"""CV pipeline orchestration: sanitize -> detect -> extract -> validate -> score (proposed) -> persist.

Nothing here can send, book or release anything. Scores are stored as `proposed`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone

import fitz

from ..config import MAX_PDF_PAGES, MAX_UPLOAD_BYTES, UPLOAD_DIR
from ..contracts import CVExtraction, SanitizeResult, ScoreOutput, ValidatedCV
from ..db import connect, register_schema, tx
from .detector import detect
from .extractor import extract_cv
from .sanitizer import SanitizeError, sanitize
from .validator import validate

log = logging.getLogger("hireguard.pipeline")

EMAIL_RX = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
JOB_RX = re.compile(r"^[A-Z0-9-]{3,32}$")
CAND_RX = re.compile(r"^CAND-[A-Z0-9-]{3,32}$")


class UploadRejected(ValueError):
    pass


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,              -- ok | needs_human
            doc_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS candidates_job ON candidates(job_id);
        CREATE TABLE IF NOT EXISTS pipeline_docs (
            doc_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
            sha256 TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            visible_text TEXT NOT NULL,
            page_offsets TEXT NOT NULL,
            hidden_findings TEXT NOT NULL,
            validated TEXT NOT NULL,
            score TEXT,
            extraction_source TEXT NOT NULL    -- llm | none | ground_truth (offline demo seed)
        );
        """
    )


def check_upload(pdf_bytes: bytes) -> int:
    """Size, magic bytes, parseable, not encrypted, page limit. Returns page count."""
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise UploadRejected(f"file larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise UploadRejected("not a PDF file")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        raise UploadRejected("unreadable PDF")
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise UploadRejected("encrypted PDFs are not accepted")
        if doc.page_count < 1 or doc.page_count > MAX_PDF_PAGES:
            raise UploadRejected(f"PDF must have 1-{MAX_PDF_PAGES} pages")
        return doc.page_count
    finally:
        doc.close()


def check_meta(name: str, email: str, job_id: str):
    if not name or len(name) > 120 or any(c in name for c in "<>\x00"):
        raise UploadRejected("invalid name")
    if not EMAIL_RX.match(email or ""):
        raise UploadRejected("invalid email")
    if not JOB_RX.match(job_id or ""):
        raise UploadRejected("invalid job_id")


def _score(validated: ValidatedCV, job_id: str) -> ScoreOutput | None:
    try:
        from ..scoring.jobs import get_rubric  # P2
        from ..scoring.scorer import score
    except ImportError as e:
        log.warning("scorer not available yet: %s", e)
        return None
    try:
        s = score(validated, get_rubric(job_id))
    except KeyError:
        log.warning("no rubric for job %s", job_id)
        return None
    try:
        from ..scoring.routes import save_score  # P2's table is the source of truth for rescoring
        save_score(s)
    except ImportError:
        pass
    return s


def _audit(action: str, cid: str, details: dict):
    try:
        from ..workflow.audit import append  # P3
        append("system:pipeline", action, "candidate", cid, details)
    except Exception as e:  # audit must not be silently skipped in prod; here P3 may not be ready yet
        log.warning("audit append failed: %s", e)


def process_cv(pdf_bytes: bytes, name: str, email: str, job_id: str, candidate_id: str | None = None,
               actor: str = "system", extraction_override: CVExtraction | None = None) -> dict:
    """Runs the whole pipeline and persists it. Returns CandidateDetail (API.md)."""
    check_meta(name, email, job_id)
    check_upload(pdf_bytes)
    cid = candidate_id or f"CAND-{uuid.uuid4().hex[:10].upper()}"
    if not CAND_RX.match(cid):
        raise UploadRejected("invalid candidate id")
    doc_id = uuid.uuid4().hex
    try:
        san = sanitize(pdf_bytes, doc_id=doc_id)
    except SanitizeError as e:
        raise UploadRejected(str(e))

    flags = detect(san.visible_text, san.hidden_findings)
    if extraction_override is not None:
        extraction, source = extraction_override, "ground_truth"
    else:
        extraction = extract_cv(san.visible_text)
        source = "llm" if extraction else "none"
    validated = validate(cid, san, extraction, flags)
    score = _score(validated, job_id)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    with tx() as conn:
        old = conn.execute("SELECT doc_id FROM candidates WHERE candidate_id = ?", (cid,)).fetchone()
        if old:
            conn.execute("DELETE FROM pipeline_docs WHERE candidate_id = ?", (cid,))
            conn.execute("DELETE FROM candidates WHERE candidate_id = ?", (cid,))
        conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?)",
                     (cid, name, email.lower(), job_id, validated.status, doc_id,
                      datetime.now(timezone.utc).isoformat()))
        conn.execute("INSERT INTO pipeline_docs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (doc_id, cid, san.sha256, str(pdf_path), san.page_count, san.visible_text,
                      json.dumps(san.page_offsets), json.dumps([f.model_dump() for f in san.hidden_findings]),
                      validated.model_dump_json(), score.model_dump_json() if score else None, source))
    _audit("pipeline.process_cv", cid, {
        "actor": actor, "job_id": job_id, "sha256": san.sha256, "status": validated.status,
        "hidden_findings": len(san.hidden_findings), "injection_flags": len(flags),
        "dropped": len(validated.dropped), "extraction": source,
        "score_total": score.total if score else None,
    })
    try:
        from ..scoring.money import record_activity  # P2 money dashboard
        record_activity("cv_screening")
    except ImportError:
        pass
    return get_candidate(cid)

# ---------------------------------------------------------------- reads


def _latest_score(conn, cid: str, job_id: str, fallback: str | None) -> dict | None:
    try:
        r = conn.execute("SELECT score_json FROM score_results WHERE candidate_id = ? AND job_id = ?",
                         (cid, job_id)).fetchone()
        if r:
            return json.loads(r["score_json"])
    except sqlite3.OperationalError:
        pass  # P2 table not created yet
    return json.loads(fallback) if fallback else None


def _row(conn, r) -> dict:
    validated = json.loads(r["validated"])
    hidden = json.loads(r["hidden_findings"])
    return {
        "candidate_id": r["candidate_id"], "name": r["name"], "email": r["email"], "job_id": r["job_id"],
        "status": r["status"], "score": _latest_score(conn, r["candidate_id"], r["job_id"], r["score"]),
        "flags": len(validated.get("injection_flags", [])), "hidden": len(hidden),
        "extraction": r["extraction_source"],  # llm | none | ground_truth: the UI never shows offline output as a model run
        "_validated": validated, "_hidden": hidden, "_page_count": r["page_count"],
    }


_SELECT = """SELECT c.*, d.validated, d.hidden_findings, d.score, d.page_count, d.extraction_source
             FROM candidates c JOIN pipeline_docs d ON d.doc_id = c.doc_id"""


def list_candidates(job_id: str | None = None) -> list[dict]:
    conn = connect()
    try:
        q, args = (_SELECT + " WHERE c.job_id = ?", (job_id,)) if job_id else (_SELECT, ())
        rows = [_row(conn, r) for r in conn.execute(q, args)]
    finally:
        conn.close()
    rows.sort(key=lambda x: (-(x["score"]["total"] if x["score"] else -1), x["candidate_id"]))
    for x in rows:
        for k in ("_validated", "_hidden", "_page_count"):
            x.pop(k)
    return rows


def get_candidate(cid: str) -> dict | None:
    conn = connect()
    try:
        r = conn.execute(_SELECT + " WHERE c.candidate_id = ?", (cid,)).fetchone()
        if not r:
            return None
        x = _row(conn, r)
    finally:
        conn.close()
    x["validated"], x["hidden_findings"], x["page_count"] = x.pop("_validated"), x.pop("_hidden"), x.pop("_page_count")
    return x


def get_text(cid: str) -> dict | None:
    conn = connect()
    try:
        r = conn.execute("SELECT d.visible_text, d.page_offsets FROM candidates c JOIN pipeline_docs d "
                         "ON d.doc_id = c.doc_id WHERE c.candidate_id = ?", (cid,)).fetchone()
    finally:
        conn.close()
    return {"visible_text": r["visible_text"], "page_offsets": json.loads(r["page_offsets"])} if r else None


def get_pdf_path(cid: str):
    conn = connect()
    try:
        r = conn.execute("SELECT d.pdf_path FROM candidates c JOIN pipeline_docs d ON d.doc_id = c.doc_id "
                         "WHERE c.candidate_id = ?", (cid,)).fetchone()
    finally:
        conn.close()
    return r["pdf_path"] if r else None


def security_findings() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(_SELECT).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        hidden = json.loads(r["hidden_findings"])
        flags = json.loads(r["validated"]).get("injection_flags", [])
        if hidden or flags:
            # blocked: hidden content never reached the model and flags never touch the score
            out.append({"candidate_id": r["candidate_id"], "name": r["name"], "job_id": r["job_id"],
                        "hidden_findings": hidden, "injection_flags": flags, "blocked": True})
    out.sort(key=lambda x: (-len(x["injection_flags"]) - len(x["hidden_findings"]), x["candidate_id"]))
    return out

# ---------------------------------------------------------------- for P2 (rescore / eval)


def list_validated(job_id: str) -> list[ValidatedCV]:
    conn = connect()
    try:
        rows = conn.execute("SELECT d.validated FROM candidates c JOIN pipeline_docs d ON d.doc_id = c.doc_id "
                            "WHERE c.job_id = ?", (job_id,)).fetchall()
    finally:
        conn.close()
    return [ValidatedCV.model_validate_json(r["validated"]) for r in rows]


def analyze_pdf(pdf_bytes: bytes, candidate_id: str,
                extraction: CVExtraction | None = None) -> tuple[SanitizeResult, ValidatedCV]:
    """Pure: no DB, no files, no audit. For P2's eval harness."""
    san = sanitize(pdf_bytes)
    flags = detect(san.visible_text, san.hidden_findings)
    if extraction is None:
        extraction = extract_cv(san.visible_text)
    return san, validate(candidate_id, san, extraction, flags)

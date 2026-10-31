"""Email gate: code rules decide the lane. The model only fills intent/urgency/language enums
and never judges whether its input is an attack.

Lanes: suspicious (auth failed or forged identity, held, no candidate data ever)
       needs_human (unknown sender, extraction failed, sensitive intent, high urgency)
       routine (verified candidate, drafted reply goes to the approval queue)

Authentication: live mode (HG_EMAIL_LIVE_AUTH=1) runs `authheaders` (DKIM + DMARC, SPF when the client IP is known).
Offline/demo mode trusts only the Authentication-Results header stamped by OUR receiving MTA (authserv-id
HG_AUTHSERV_ID). A sender can forge an Authentication-Results header with any other authserv-id, and those are ignored.
"""
import email
import html
import json
import os
import re
import sqlite3
from email import policy
from email.utils import getaddresses, parseaddr

from fastapi import HTTPException

from ..contracts import EmailExtraction, EmailIntent, Urgency
from ..db import connect, register_schema, tx
from . import audit, drafting
from .common import canonical_json, new_id, now_iso, table_exists

AUTHSERV_ID = os.getenv("HG_AUTHSERV_ID", "mx.hireguard.demo")
LIVE_AUTH = os.getenv("HG_EMAIL_LIVE_AUTH", "0") == "1"
MAX_BODY_CHARS = 20_000

NEEDS_HUMAN_INTENTS = {EmailIntent.withdraw, EmailIntent.other, EmailIntent.document_request, EmailIntent.leave_request}
_AR_RESULT = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I)


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inbox_items (
            id TEXT PRIMARY KEY,
            message_id TEXT UNIQUE,
            received_at TEXT NOT NULL,
            from_addr TEXT NOT NULL,
            from_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            spf TEXT NOT NULL, dkim TEXT NOT NULL, dmarc TEXT NOT NULL,
            language TEXT, intent TEXT, urgency TEXT,
            lane TEXT NOT NULL CHECK (lane IN ('routine','needs_human','suspicious')),
            reasons TEXT NOT NULL,
            candidate_id TEXT,
            status TEXT NOT NULL,
            draft_item_ids TEXT NOT NULL DEFAULT '[]'
        );
        """
    )

# ---------------------------------------------------------------- authentication


def parse_auth_results(msg) -> dict[str, str] | None:
    """Results from the first Authentication-Results header carrying OUR authserv-id, or None."""
    for header in msg.get_all("Authentication-Results", []) or []:
        value = str(header)
        authserv = value.split(";", 1)[0].strip().split()[0] if value.strip() else ""
        if authserv.lower() != AUTHSERV_ID.lower():
            continue
        res = {"spf": "none", "dkim": "none", "dmarc": "none"}
        for k, v in _AR_RESULT.findall(value):
            if res[k.lower()] == "none":  # first result per method wins
                res[k.lower()] = v.lower()
        return res
    return None


def authenticate(raw: bytes, msg, client_ip: str | None = None) -> dict[str, str] | None:
    if LIVE_AUTH:
        from authheaders import authenticate_message  # network: DNS lookups for DKIM keys / DMARC policy
        header = authenticate_message(raw, AUTHSERV_ID, ip=client_ip, mail_from=parseaddr(msg.get("From", ""))[1],
                                      spf=client_ip is not None, dkim=True, dmarc=True)
        return parse_auth_results(email.message_from_bytes(header.encode() + b"\r\n\r\n", policy=policy.default))
    return parse_auth_results(msg)

# ---------------------------------------------------------------- helpers


def _body_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text[:MAX_BODY_CHARS]


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def _verified_candidate(conn, addr: str) -> dict | None:
    """Exact match against the verified address from the intake form (P1's `candidates` table)."""
    if not addr or not table_exists(conn, "candidates"):
        return None
    try:
        r = conn.execute("SELECT * FROM candidates WHERE lower(email) = ?", (addr.lower(),)).fetchone()
    except sqlite3.OperationalError:
        return None
    if not r:
        return None
    r = dict(r)
    return {"candidate_id": r["candidate_id"], "email": r["email"], "name": r.get("name") or "",
            "job_id": r.get("job_id") or "", "status": r.get("status")}


def _extract(body: str) -> EmailExtraction | None:
    try:
        from ..pipeline.email_extract import extract_email  # P1, lazy: the gate works before P1 lands
        return extract_email(body)
    except Exception:
        return None

# ---------------------------------------------------------------- gate


def classify(msg, auth: dict | None, extraction: EmailExtraction | None, candidate_found: bool) -> tuple[str, list[str]]:
    """Pure rules. Returns (lane, reasons)."""
    suspicious, needs_human = [], []
    if auth is None:
        suspicious.append("no_trusted_auth_results")
    elif auth["dmarc"] != "pass":
        suspicious.append(f"dmarc_{auth['dmarc']}")
    name, addr = parseaddr(str(msg.get("From", "")))
    if "@" in name and parseaddr(name)[1].lower() != addr.lower():
        suspicious.append("display_name_contains_other_address")
    if len(getaddresses([str(v) for v in msg.get_all("From", [])])) != 1:
        suspicious.append("multiple_from_addresses")
    reply_to = parseaddr(str(msg.get("Reply-To", "")))[1]
    if reply_to and _domain(reply_to) != _domain(addr):
        suspicious.append("reply_to_domain_mismatch")

    if not candidate_found:
        needs_human.append("sender_not_a_verified_candidate")
    if extraction is None:
        needs_human.append("extraction_failed")
    else:
        if extraction.intent in NEEDS_HUMAN_INTENTS:
            needs_human.append(f"intent_{extraction.intent.value}")
        if extraction.urgency == Urgency.high:
            needs_human.append("urgency_high")

    if suspicious:
        return "suspicious", suspicious + needs_human
    if needs_human:
        return "needs_human", needs_human
    return "routine", []


def ingest(raw: str | bytes, inbox_id: str | None = None, client_ip: str | None = None) -> dict:
    raw_bytes = raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else raw
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    message_id = str(msg.get("Message-ID", "")).strip() or None

    conn = connect()
    try:
        if message_id:
            r = conn.execute("SELECT id FROM inbox_items WHERE message_id = ?", (message_id,)).fetchone()
            if r:
                return get(r["id"])
    finally:
        conn.close()

    auth = authenticate(raw_bytes, msg, client_ip)
    from_name, from_addr = parseaddr(str(msg.get("From", "")))
    body = _body_text(msg)
    extraction = _extract(body)  # the reader: typed enums out, no tools, no authority

    with tx() as conn:
        # identity is resolved only after the auth rules: a spoofed sender is never matched to a candidate
        candidate = _verified_candidate(conn, from_addr)
        lane, reasons = classify(msg, auth, extraction, candidate is not None)
        if lane == "suspicious":
            candidate = None
        item_id = inbox_id or new_id("EML")
        status = {"suspicious": "held", "needs_human": "new", "routine": "drafted"}[lane]
        auth = auth or {"spf": "none", "dkim": "none", "dmarc": "none"}
        conn.execute(
            "INSERT INTO inbox_items (id, message_id, received_at, from_addr, from_name, subject, body, spf, dkim, "
            "dmarc, language, intent, urgency, lane, reasons, candidate_id, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, message_id, now_iso(), from_addr, from_name[:120], str(msg.get("Subject", ""))[:300], body,
             auth["spf"], auth["dkim"], auth["dmarc"],
             extraction.language.value if extraction else None,
             extraction.intent.value if extraction else None,
             extraction.urgency.value if extraction else None,
             lane, canonical_json(reasons), candidate["candidate_id"] if candidate else None, status))
        drafts = []
        if lane == "routine" and candidate and extraction:
            drafts = drafting.draft_reply(conn, item_id, candidate, extraction.intent, extraction.language.value)
            conn.execute("UPDATE inbox_items SET draft_item_ids = ? WHERE id = ?",
                         (canonical_json([d.id for d in drafts]), item_id))
        audit.append("system", "inbox.ingest", "inbox_item", item_id,
                     {"lane": lane, "reasons": reasons, "dmarc": auth["dmarc"], "drafts": len(drafts)}, conn=conn)
    return get(item_id)


def _serialize(r) -> dict:
    item = {
        "id": r["id"], "received_at": r["received_at"], "from": r["from_addr"], "from_name": r["from_name"],
        "subject": r["subject"], "body_preview": r["body"][:280],
        "auth": {"spf": r["spf"], "dkim": r["dkim"], "dmarc": r["dmarc"]},
        "language": r["language"], "intent": r["intent"], "urgency": r["urgency"],
        "lane": r["lane"], "reasons": json.loads(r["reasons"]), "status": r["status"],
        "candidate_id": None, "draft_item_ids": [],
    }
    if r["lane"] != "suspicious":  # spoofed sender -> no candidate data offered, ever
        item["candidate_id"] = r["candidate_id"]
        item["draft_item_ids"] = json.loads(r["draft_item_ids"])
    return item


def get(item_id: str) -> dict:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM inbox_items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not r:
        raise HTTPException(404, "inbox item not found")
    return _serialize(r)


URGENCY_ORDER = {"high": 0, "normal": 1, "low": 2, None: 3}


def digest() -> dict:
    """{lanes: {lane: [{intent, urgency, count, items[]}]}}, grouped by intent and urgency, most urgent first."""
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM inbox_items WHERE status != 'archived' ORDER BY received_at DESC").fetchall()
    finally:
        conn.close()
    lanes: dict[str, dict] = {"routine": {}, "needs_human": {}, "suspicious": {}}
    for r in rows:
        key = (r["intent"], r["urgency"])
        g = lanes[r["lane"]].setdefault(key, {"intent": r["intent"], "urgency": r["urgency"], "count": 0, "items": []})
        g["count"] += 1
        g["items"].append(_serialize(r))
    return {"lanes": {lane: sorted(groups.values(), key=lambda g: (URGENCY_ORDER.get(g["urgency"], 3), g["intent"] or ""))
                      for lane, groups in lanes.items()}}

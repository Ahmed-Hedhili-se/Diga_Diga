"""Risk-scored approval queue. Code computes risk; humans decide; every decision is audited.

- risk >= 50 -> "high": shown one by one. Otherwise "routine": batched by kind (one batch per kind per day).
- Every CANARY_EVERY-th real item, a canary (a copy with a planted defect) is added to the same batch.
  `is_canary` / `canary_defect` are stored server-side only and never serialized. Approving a canary = a miss.
- Offers need 2 distinct hr_manager approvers. Nobody approves an item they created.
"""
import copy
import json
import re
import sqlite3
from typing import Any

from fastapi import HTTPException

from ..config import CANARY_EVERY
from ..contracts import ApprovalItem, ApprovalKind, ApprovalStatus, Decision, Role, UserOut
from ..db import connect, register_schema, tx
from . import attention, audit
from .common import canonical_json, new_id, now, now_iso

HIGH_RISK_THRESHOLD = 50

BASE_RISK = {
    ApprovalKind.email_send: 20,
    ApprovalKind.interview_booking: 15,
    ApprovalKind.status_change: 30,
    ApprovalKind.shortlist_commit: 40,
    ApprovalKind.document_release: 25,
    ApprovalKind.held_email_release: 60,
    ApprovalKind.leave_request: 20,
    ApprovalKind.offer: 70,
}

REQUIRED_APPROVALS = {ApprovalKind.offer: 2}

# who may see and decide each kind (recruiters never touch offers, HR documents or leave)
DECIDERS = {
    ApprovalKind.offer: {Role.hr_manager},
    ApprovalKind.document_release: {Role.hr_manager},
    ApprovalKind.leave_request: {Role.hr_manager},
    ApprovalKind.held_email_release: {Role.hr_manager},
}
DEFAULT_DECIDERS = {Role.recruiter, Role.hr_manager}


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_items (
            id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            risk INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            batch_id TEXT,
            title TEXT NOT NULL,
            payload TEXT NOT NULL,
            diff TEXT,
            required_approvals INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            is_canary INTEGER NOT NULL DEFAULT 0,
            canary_defect TEXT
        );
        CREATE INDEX IF NOT EXISTS approval_items_status ON approval_items(status, risk_level, kind);
        CREATE TABLE IF NOT EXISTS approval_decisions (
            item_id TEXT NOT NULL REFERENCES approval_items(id),
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('approve','reject')),
            at TEXT NOT NULL,
            UNIQUE (item_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS approval_canary_results (
            item_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('hit','miss')),
            at TEXT NOT NULL
        );
        """
    )


# The sanitizer reports an undecodable glyph (U+FFFD, common in Arabic words inside FR/EN CVs) as a zero_width
# finding whose text is only "[N undecodable glyphs] near: ...". That is not hidden content.
_UNDECODABLE_ONLY = re.compile(r"^\[\d+ undecodable glyphs?\]")


def _is_high_finding(f: Any) -> bool:
    """High unless the sanitizer marked it `severity: "low"`, or it is a zero_width finding that is only
    undecodable glyphs. A missing field or an unknown shape means high (fail closed)."""
    if not isinstance(f, dict):
        return True
    if f.get("severity") == "low":
        return False
    return not (f.get("channel") == "zero_width" and _UNDECODABLE_ONLY.match(str(f.get("text", ""))))


def count_high_findings(payload: dict[str, Any]) -> int:
    """`hidden_findings_high` (int) wins. Otherwise `hidden_findings` is a list of finding dicts, or a legacy int
    count that can't be told apart and so counts as high."""
    if "hidden_findings_high" in payload:
        return int(payload["hidden_findings_high"] or 0)
    findings = payload.get("hidden_findings", 0)
    if isinstance(findings, (list, tuple)):
        return sum(_is_high_finding(f) for f in findings)
    return int(findings) if isinstance(findings, int) else 0


def compute_risk(kind: ApprovalKind, payload: dict[str, Any]) -> int:
    """Code rules only. The model never judges whether its input is an attack."""
    r = BASE_RISK[kind]
    if payload.get("suspicious"):
        r += 40
    if payload.get("needs_human"):
        r += 20
    if payload.get("recipient_verified") is False:
        r += 30
    if payload.get("injection_flags", 0):
        r += 20
    if count_high_findings(payload) > 0:  # low-severity findings (undecodable glyphs) add nothing
        r += 10
    return max(0, min(100, r))


def _batch_id(kind: ApprovalKind) -> str:
    return f"B-{kind.value}-{now().strftime('%Y%m%d')}"


def _row_to_item(r, decisions: list) -> ApprovalItem:
    # deliberately no is_canary / canary_defect here
    return ApprovalItem(
        id=r["id"], kind=r["kind"], risk=r["risk"], risk_level=r["risk_level"], batch_id=r["batch_id"],
        title=r["title"], payload=json.loads(r["payload"]), diff=json.loads(r["diff"]) if r["diff"] else None,
        required_approvals=r["required_approvals"], status=r["status"], created_at=r["created_at"],
        created_by=r["created_by"],
        decisions=[Decision(user_id=d["user_id"], decision=d["decision"], at=d["at"]) for d in decisions],
    )


def _insert(conn, kind: ApprovalKind, title: str, payload: dict, created_by: str, risk: int,
            diff: dict | None, is_canary: bool = False, canary_defect: str | None = None) -> str:
    seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM approval_items").fetchone()[0]
    item_id = new_id("APR")
    level = "high" if risk >= HIGH_RISK_THRESHOLD else "routine"
    conn.execute(
        "INSERT INTO approval_items (id, seq, kind, risk, risk_level, batch_id, title, payload, diff, "
        "required_approvals, status, created_at, created_by, is_canary, canary_defect) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, seq, kind.value, risk, level, _batch_id(kind) if level == "routine" else None, title,
         canonical_json(payload), canonical_json(diff) if diff is not None else None,
         REQUIRED_APPROVALS.get(kind, 1), ApprovalStatus.pending.value, now_iso(), created_by,
         int(is_canary), canary_defect),
    )
    return item_id


def _make_canary(kind: ApprovalKind, title: str, payload: dict, diff: dict | None) -> tuple[dict, dict | None, str]:
    """A plausible twin with one planted defect a careful reviewer should catch in the diff."""
    p, d = copy.deepcopy(payload), copy.deepcopy(diff) if diff else None
    if "to" in p:
        p["to"] = "candidate.records@mail-transfer.example"
        if d and isinstance(d.get("after"), dict):
            d["after"]["to"] = p["to"]
        return p, d, "recipient swapped to unverified external address"
    if "candidate_ids" in p and p["candidate_ids"]:
        p["candidate_ids"] = list(p["candidate_ids"]) + ["CAND-999"]
        return p, d, "unknown candidate appended to shortlist"
    if "slot" in p:
        p["slot"] = {"start": "2026-12-25T03:00:00+01:00", "end": "2026-12-25T03:45:00+01:00"}
        return p, d, "interview at 03:00 on a public holiday"
    p["status_to"] = "rejected"
    return p, d, "status set to rejected without reason"


def create_item(kind: ApprovalKind | str, title: str, payload: dict[str, Any], created_by: str,
                risk: int | None = None, diff: dict[str, Any] | None = None,
                conn: sqlite3.Connection | None = None) -> ApprovalItem:
    if conn is None:
        with tx() as c:
            return create_item(kind, title, payload, created_by, risk, diff, conn=c)
    kind = ApprovalKind(kind)
    computed = compute_risk(kind, payload)
    risk = max(computed, risk or 0)  # a caller can raise risk, never lower it
    item_id = _insert(conn, kind, title, payload, created_by, risk, diff)
    audit.append(created_by, "approval.create", "approval_item", item_id,
                 {"kind": kind.value, "risk": risk, "title": title}, conn=conn)

    real_count = conn.execute("SELECT COUNT(*) FROM approval_items WHERE is_canary = 0").fetchone()[0]
    if CANARY_EVERY > 0 and real_count % CANARY_EVERY == 0:
        cp, cd, defect = _make_canary(kind, title, payload, diff)
        canary_id = _insert(conn, kind, title, cp, created_by, min(risk, HIGH_RISK_THRESHOLD - 1), cd,
                            is_canary=True, canary_defect=defect)
        # the audit entry looks like a normal create: reviewers can read the audit log
        audit.append(created_by, "approval.create", "approval_item", canary_id,
                     {"kind": kind.value, "risk": min(risk, HIGH_RISK_THRESHOLD - 1), "title": title}, conn=conn)
    return get_item(item_id, conn=conn)


def _load(conn, item_id: str):
    r = conn.execute("SELECT * FROM approval_items WHERE id = ?", (item_id,)).fetchone()
    if not r:
        raise HTTPException(404, "approval item not found")
    return r


def get_item(item_id: str, conn: sqlite3.Connection | None = None) -> ApprovalItem:
    own = conn is None
    conn = conn or connect()
    try:
        r = _load(conn, item_id)
        ds = conn.execute("SELECT * FROM approval_decisions WHERE item_id = ? ORDER BY at", (item_id,)).fetchall()
        return _row_to_item(r, ds)
    finally:
        if own:
            conn.close()


def can_decide(user: UserOut, kind: ApprovalKind | str) -> bool:
    return user.role in DECIDERS.get(ApprovalKind(kind), DEFAULT_DECIDERS)


def decide(item_id: str, user: UserOut, decision: str, conn: sqlite3.Connection | None = None,
           batch_size: int = 1) -> ApprovalItem:
    if conn is None:
        with tx() as c:
            return decide(item_id, user, decision, conn=c, batch_size=batch_size)
    if decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    r = _load(conn, item_id)
    kind = ApprovalKind(r["kind"])
    if not can_decide(user, kind):
        raise HTTPException(403, "your role cannot decide this item")
    if r["status"] != ApprovalStatus.pending.value:
        raise HTTPException(409, f"item is {r['status']}")
    if r["created_by"] == user.id:
        raise HTTPException(403, "you cannot approve an item you created")
    if conn.execute("SELECT 1 FROM approval_decisions WHERE item_id=? AND user_id=?", (item_id, user.id)).fetchone():
        raise HTTPException(409, "you already decided this item; a second, different approver is required")

    at = now_iso()
    conn.execute("INSERT INTO approval_decisions VALUES (?,?,?,?,?)", (item_id, user.id, user.role.value, decision, at))
    attention.record(conn, item_id, user.id, batch_size, at)

    if r["is_canary"]:
        outcome = "miss" if decision == "approve" else "hit"
        conn.execute("INSERT INTO approval_canary_results VALUES (?,?,?,?)", (item_id, user.id, outcome, at))

    if decision == "reject":
        new_status = ApprovalStatus.rejected
    else:
        approvals = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM approval_decisions WHERE item_id=? AND decision='approve'", (item_id,)
        ).fetchone()[0]
        new_status = ApprovalStatus.approved if approvals >= r["required_approvals"] else ApprovalStatus.pending
    conn.execute("UPDATE approval_items SET status = ? WHERE id = ?", (new_status.value, item_id))
    audit.append(user.id, f"approval.{decision}", "approval_item", item_id,
                 {"kind": kind.value, "status": new_status.value, "role": user.role.value}, conn=conn)
    return get_item(item_id, conn=conn)


def decide_batch(batch_id: str, item_ids: list[str], user: UserOut, decision: str) -> list[ApprovalItem]:
    with tx() as conn:
        cap = attention.max_batch_size(conn)
        if decision == "approve" and len(item_ids) > cap:
            # rejecting in bulk is always allowed; approving in bulk is limited by the attention guard
            raise HTTPException(422, f"attention guard: approve at most {cap} items per batch right now "
                                     f"(recent canaries were missed)")
        out = []
        for item_id in item_ids:
            r = _load(conn, item_id)
            if r["batch_id"] != batch_id:
                raise HTTPException(400, f"{item_id} is not in batch {batch_id}")
            out.append(decide(item_id, user, decision, conn=conn, batch_size=len(item_ids)))
        return out


def queue(user: UserOut) -> dict:
    """Pending items the user may decide: routine ones grouped into batches, high-risk ones listed alone."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM approval_items WHERE status = 'pending' ORDER BY risk DESC, seq"
        ).fetchall()
        batches: dict[str, dict] = {}
        high = []
        for r in rows:
            if not can_decide(user, r["kind"]):
                continue
            ds = conn.execute("SELECT * FROM approval_decisions WHERE item_id = ?", (r["id"],)).fetchall()
            item = _row_to_item(r, ds)
            if r["risk_level"] == "high":
                high.append(item)
            else:
                b = batches.setdefault(r["batch_id"], {"batch_id": r["batch_id"], "kind": r["kind"], "items": []})
                b["items"].append(item)
        cap = attention.max_batch_size(conn)
        chunks = []  # the attention guard splits each day's batch into reviewable chunks
        for b in batches.values():
            for i in range(0, len(b["items"]), cap):
                chunks.append(b | {"items": b["items"][i:i + cap], "chunk": i // cap})
        return {"batches": chunks, "high_risk": high, "max_batch_size": cap}
    finally:
        conn.close()


def is_canary(item_id: str, conn: sqlite3.Connection) -> bool:
    """Server-side only (executor). Never expose through an API."""
    r = conn.execute("SELECT is_canary FROM approval_items WHERE id = ?", (item_id,)).fetchone()
    return bool(r and r["is_canary"])


def reviewer_stats() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT user_id,
                      SUM(outcome = 'hit') AS caught,
                      SUM(outcome = 'miss') AS missed
               FROM approval_canary_results GROUP BY user_id"""
        ).fetchall()
        totals = conn.execute(
            "SELECT user_id, COUNT(*) AS decisions FROM approval_decisions GROUP BY user_id"
        ).fetchall()
    finally:
        conn.close()
    dec = {t["user_id"]: t["decisions"] for t in totals}
    out = {uid: {"user_id": uid, "decisions": n, "canaries_caught": 0, "canaries_missed": 0} for uid, n in dec.items()}
    for r in rows:
        out.setdefault(r["user_id"], {"user_id": r["user_id"], "decisions": 0})
        out[r["user_id"]].update(canaries_caught=r["caught"] or 0, canaries_missed=r["missed"] or 0)
    return list(out.values())

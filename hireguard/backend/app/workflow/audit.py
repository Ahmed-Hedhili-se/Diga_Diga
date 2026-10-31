"""Append-only, hash-chained audit log.

Demo: SQLite triggers abort any UPDATE/DELETE. Production: Postgres, the app role has INSERT/SELECT only,
plus the same triggers (see docs/threat_model.md). Every entry hashes the previous one, so editing a row
with raw DB access breaks `verify()` from that row on; anchors (anchor.py) pin the head externally.
"""
import hashlib
import json
import sqlite3
from typing import Any

from ..contracts import AuditEntry
from ..db import connect, register_schema, tx
from .common import canonical_json, now_iso

GENESIS = "0" * 64


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            details TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL UNIQUE
        );
        CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

        CREATE TABLE IF NOT EXISTS audit_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            seq INTEGER NOT NULL,
            head_hash TEXT NOT NULL,
            method TEXT NOT NULL,     -- "file", "file+ots", "file+ots+git"
            status TEXT NOT NULL      -- "anchored" | "pending"
        );
        CREATE TRIGGER IF NOT EXISTS audit_anchors_no_update BEFORE UPDATE ON audit_anchors
        BEGIN SELECT RAISE(ABORT, 'audit_anchors is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_anchors_no_delete BEFORE DELETE ON audit_anchors
        BEGIN SELECT RAISE(ABORT, 'audit_anchors is append-only'); END;
        """
    )


def _entry_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


def _body(seq: int, ts: str, actor: str, action: str, object_type: str, object_id: str, details: dict) -> dict:
    return {"seq": seq, "ts": ts, "actor": actor, "action": action,
            "object_type": object_type, "object_id": object_id, "details": details}


def append(actor: str, action: str, object_type: str, object_id: str, details: dict[str, Any] | None = None,
           conn: sqlite3.Connection | None = None) -> AuditEntry:
    """Pass `conn` to write inside the caller's transaction (so the action and its audit commit together)."""
    if conn is None:
        with tx() as c:
            return append(actor, action, object_type, object_id, details, conn=c)
    details = json.loads(canonical_json(details or {}))  # normalise types so verify() recomputes the same bytes
    last = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    seq = (last["seq"] + 1) if last else 1
    prev = last["hash"] if last else GENESIS
    ts = now_iso()
    h = _entry_hash(prev, _body(seq, ts, actor, action, object_type, object_id, details))
    conn.execute(
        "INSERT INTO audit_log (seq, ts, actor, action, object_type, object_id, details, prev_hash, hash) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (seq, ts, actor, action, object_type, object_id, canonical_json(details), prev, h),
    )
    return AuditEntry(seq=seq, ts=ts, actor=actor, action=action, object_type=object_type,
                      object_id=object_id, details=details, prev_hash=prev, hash=h)


def _row_to_entry(r) -> AuditEntry:
    return AuditEntry(seq=r["seq"], ts=r["ts"], actor=r["actor"], action=r["action"], object_type=r["object_type"],
                      object_id=r["object_id"], details=json.loads(r["details"]), prev_hash=r["prev_hash"], hash=r["hash"])


def list_entries(limit: int = 100) -> list[AuditEntry]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (max(1, min(limit, 1000)),)).fetchall()
    finally:
        conn.close()
    return [_row_to_entry(r) for r in rows]


def head(conn: sqlite3.Connection) -> tuple[int, str]:
    last = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    return (last["seq"], last["hash"]) if last else (0, GENESIS)


def verify() -> dict:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
        anchor = conn.execute("SELECT * FROM audit_anchors ORDER BY id DESC LIMIT 1").fetchone()
        anchors = conn.execute("SELECT seq, head_hash FROM audit_anchors").fetchall()
    finally:
        conn.close()
    prev, broken_at, expected_seq = GENESIS, None, 1
    hashes = {}
    for r in rows:
        body = _body(r["seq"], r["ts"], r["actor"], r["action"], r["object_type"], r["object_id"], json.loads(r["details"]))
        if r["seq"] != expected_seq or r["prev_hash"] != prev or _entry_hash(prev, body) != r["hash"]:
            broken_at = r["seq"]
            break
        hashes[r["seq"]] = r["hash"]
        prev, expected_seq = r["hash"], expected_seq + 1
    # an anchored head that no longer matches = rewritten history (or truncation)
    if broken_at is None:
        for a in anchors:
            if hashes.get(a["seq"]) != a["head_hash"]:
                broken_at = a["seq"]
                break
    return {
        "ok": broken_at is None,
        "length": len(rows),
        "broken_at": broken_at,
        "last_anchor": dict(anchor) if anchor else None,
    }

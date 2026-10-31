import json
import secrets
from datetime import datetime, timezone
from typing import Any


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def canonical_json(obj: Any) -> str:
    """Deterministic JSON for hashing: sorted keys, no whitespace, UTF-8 kept."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def one_line(value: str, max_len: int = 80) -> str:
    """Slot values go into email headers/bodies: no newlines, bounded length."""
    return " ".join(str(value).split())[:max_len]


def table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

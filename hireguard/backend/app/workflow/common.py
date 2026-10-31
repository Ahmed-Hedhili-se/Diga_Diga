import json
import secrets
import unicodedata
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


_BIDI_CONTROLS = {chr(c) for c in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069)}  # reorder visible text


def one_line(value: str, max_len: int = 80) -> str:
    """Slot values go into email headers/bodies: one line, no control characters, bounded length.
    Control chars (NUL, ESC, CR/LF, U+2028/2029/0085) and bidi overrides become spaces; ZWNJ/ZWJ/LRM/RLM stay
    because Arabic and Persian names use them."""
    cleaned = "".join(" " if unicodedata.category(c) in ("Cc", "Zl", "Zp") or c in _BIDI_CONTROLS else c
                      for c in str(value))
    return " ".join(cleaned.split())[:max_len]


def table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

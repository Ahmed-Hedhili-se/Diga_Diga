"""One SQLite file for the demo. Each module registers its own schema via `register_schema`.

Modules own their tables:
  auth_*      -> P4      pipeline_* / candidates -> P1
  score_*     -> P2      approval_* / audit_* / email_* / doc_* -> P3
"""
import sqlite3
from contextlib import contextmanager
from typing import Callable

from .config import DB_PATH

_schemas: list[Callable[[sqlite3.Connection], None]] = []


def register_schema(fn: Callable[[sqlite3.Connection], None]):
    _schemas.append(fn)
    return fn


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db():
    conn = connect()
    try:
        for fn in _schemas:
            fn(conn)
    finally:
        conn.close()

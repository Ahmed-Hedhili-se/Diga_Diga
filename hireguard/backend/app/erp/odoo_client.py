"""Minimal Odoo XML-RPC client (stdlib only). Every network or RPC failure surfaces as `OdooError`.

Config is read from module globals at call time, so tests can monkeypatch them.
"""
from __future__ import annotations

import http.client
import os
import xmlrpc.client
from functools import lru_cache
from typing import Any

ENABLED = os.getenv("HG_ODOO_ENABLED", "0") == "1"
URL = os.getenv("HG_ODOO_URL", "http://localhost:8069").rstrip("/")
DB = os.getenv("HG_ODOO_DB", "hireguard")
USER = os.getenv("HG_ODOO_USER", "hireguard-bot@example.tn")
API_KEY = os.getenv("HG_ODOO_API_KEY", "")
TIMEOUT_S = float(os.getenv("HG_ODOO_TIMEOUT_S", "10"))
SHORTLIST_STAGE = os.getenv("HG_ODOO_SHORTLIST_STAGE", "Shortlisted (HireGuard)")

MAX_ERROR_CHARS = 300  # Odoo faults can carry whole server tracebacks


class OdooError(RuntimeError):
    pass


class _Transport(xmlrpc.client.Transport):
    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = TIMEOUT_S
        return conn


class _SafeTransport(xmlrpc.client.SafeTransport):
    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = TIMEOUT_S
        return conn


def _proxy(endpoint: str) -> xmlrpc.client.ServerProxy:
    transport = _SafeTransport() if URL.startswith("https://") else _Transport()
    return xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/{endpoint}", transport=transport, allow_none=True)


def _short(e: Exception) -> str:
    msg = e.faultString if isinstance(e, xmlrpc.client.Fault) else str(e)
    msg = msg.strip().splitlines()[-1] if msg.strip() else type(e).__name__
    return msg[:MAX_ERROR_CHARS]


def _rpc(fn, *args):
    try:
        return fn(*args)
    except (OSError, http.client.HTTPException, xmlrpc.client.Error) as e:  # OSError covers timeouts/refused
        raise OdooError(_short(e)) from e


@lru_cache(maxsize=1)
def _uid() -> int:
    if not API_KEY:
        raise OdooError("HG_ODOO_API_KEY is not set")
    uid = _rpc(_proxy("common").authenticate, DB, USER, API_KEY, {})
    if not uid:
        raise OdooError(f"authentication failed for {USER} on database {DB}")
    return uid


def call(model: str, method: str, *args: Any, **kwargs: Any) -> Any:
    return _rpc(_proxy("object").execute_kw, DB, _uid(), API_KEY, model, method, list(args), kwargs)


def search_read(model: str, domain: list, fields: list[str], limit: int = 0, order: str | None = None) -> list[dict]:
    kw: dict[str, Any] = {"fields": fields}
    if limit:
        kw["limit"] = limit
    if order:
        kw["order"] = order
    return call(model, "search_read", domain, **kw)


def status() -> dict:
    """For GET /erp/status. Never raises."""
    out: dict[str, Any] = {"enabled": ENABLED, "connected": False, "url": URL, "db": DB}
    if not ENABLED:
        return out
    try:
        version = _rpc(_proxy("common").version)
        out["server_version"] = version.get("server_version") if isinstance(version, dict) else None
        out["uid"] = _uid()
        out["connected"] = True
    except OdooError as e:
        out["error"] = str(e)
    return out

"""UI <-> API contract (Yasmina/Rayen): every path the frontend calls must exist in the backend route table.

Scans hireguard/frontend/src for api(...), apiBlob(...) and downloadFile(...) calls, turns template parts into
path parameters and matches them against FastAPI's routes. Catches a renamed or removed endpoint before the demo.
"""
import re

from app.config import ROOT
from app.main import app
from route_table import api_routes

CALL = re.compile(r"\b(?:api(?:<[^>()]*>)?|apiBlob|downloadFile)\(\s*([`\"'])(/[^`\"']*)\1")


def _frontend_paths() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for f in (ROOT / "frontend" / "src").rglob("*.ts*"):
        if f.name.endswith(".test.tsx"):
            continue
        for m in CALL.finditer(f.read_text(encoding="utf-8")):
            path = re.sub(r"\$\{[^}]*\}", "{x}", m.group(2)).split("?")[0].rstrip("/") or "/"
            found.setdefault(path, []).append(f.name)
    return found


def _route_patterns() -> list[re.Pattern]:
    return [re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", r"[^/]+", re.escape(r.path)) + "$")
            for r in api_routes(app) if r.path.startswith("/api/")]


def test_frontend_calls_are_found():
    assert len(_frontend_paths()) >= 30  # the scanner still sees the client calls


def test_every_frontend_call_has_a_backend_route():
    routes = _route_patterns()
    missing = {p: files for p, files in _frontend_paths().items()
               if not any(rx.match("/api" + p.replace("{x}", "x1")) for rx in routes)}
    assert missing == {}, f"frontend calls with no backend route: {missing}"

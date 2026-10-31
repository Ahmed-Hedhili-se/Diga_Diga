"""Web hardening (P4): security headers, strict CSP, in-memory rate limits, body size caps, client IP.

Pure ASGI middleware so the body cap also covers chunked uploads.
"""
import ipaddress
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from starlette.responses import FileResponse

from .config import MAX_UPLOAD_BYTES, ROOT, TRUSTED_PROXIES

DIST = (ROOT / "frontend" / "dist").resolve()

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; "
    "frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
# Swagger UI needs inline/CDN assets; it is dev-only and gets a relaxed policy.
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
)

HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cache-control", b"no-store"),
]

# (bucket, max requests, window seconds)
LIMITS = {
    "login": (10, 60),
    "upload": (30, 60),
    "ask": (30, 60),
    "general": (300, 60),
}
JSON_BODY_MAX = 256 * 1024
UPLOAD_BODY_MAX = MAX_UPLOAD_BYTES + 64 * 1024  # multipart overhead


_PROXIES = [ipaddress.ip_network(p, strict=False) for p in TRUSTED_PROXIES]


def _is_proxy(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _PROXIES)


def client_ip(peer: str, forwarded_for: str | None) -> str:
    """The address rate limits and lockouts key on (pentest O2).

    X-Forwarded-For is believed only when the socket peer is a listed proxy (HG_TRUSTED_PROXIES); then the
    right-most hop that is not a proxy is the client. Anything malformed falls back to the peer, so a client
    can never pick its own bucket by sending the header.
    """
    if not forwarded_for or not _is_proxy(peer):
        return peer
    for hop in reversed([h.strip() for h in forwarded_for.split(",") if h.strip()]):
        if _is_proxy(hop):
            continue
        try:
            return str(ipaddress.ip_address(hop))
        except ValueError:
            return peer
    return peer


def request_ip(request) -> str:
    peer = request.client.host if request.client else "unknown"
    return client_ip(peer, request.headers.get("x-forwarded-for"))


class RateLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, bucket: str) -> tuple[bool, int]:
        limit, window = LIMITS[bucket]
        now = time.monotonic()
        with self._lock:
            q = self._hits[(key, bucket)]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (now - q[0])) + 1
            q.append(now)
            return True, 0

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def _bucket(method: str, path: str) -> str:
    if path == "/api/auth/login":
        return "login"
    if method == "POST" and path == "/api/candidates":
        return "upload"
    if path == "/api/answer-desk/ask":
        return "ask"
    return "general"


async def _send_json(send, status: int, body: dict, extra: list | None = None):
    data = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]
    headers += HEADERS + [(b"content-security-policy", CSP.encode())] + (extra or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


class _TooLarge(Exception):
    pass


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path, method = scope["path"], scope["method"]
        peer = (scope.get("client") or ("unknown", 0))[0]
        xff = b",".join(v for k, v in scope.get("headers") or [] if k == b"x-forwarded-for").decode("latin-1") or None
        client = client_ip(peer, xff)

        bucket = _bucket(method, path)
        ok, retry = limiter.allow(client, bucket)
        if not ok:
            return await _send_json(send, 429, {"detail": "rate limit exceeded"},
                                    [(b"retry-after", str(retry).encode())])

        cap = UPLOAD_BODY_MAX if bucket == "upload" else JSON_BODY_MAX
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > cap:
                    return await _send_json(send, 413, {"detail": "request body too large"})
            except ValueError:
                return await _send_json(send, 400, {"detail": "bad content-length"})

        received = 0

        async def capped_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > cap:
                    raise _TooLarge()
            return msg

        csp = DOCS_CSP if path in ("/api/docs", "/api/redoc") else CSP
        started = False

        async def secured_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
                names = {k.lower() for k, _ in msg.get("headers", [])}
                extra = [(k, v) for k, v in HEADERS if k not in names]
                extra.append((b"content-security-policy", csp.encode()))
                msg = {**msg, "headers": list(msg.get("headers", [])) + extra}
            await send(msg)

        target = self.app
        if not path.startswith("/api") and method in ("GET", "HEAD"):
            static = _static_file(path)
            if static is not None:
                target = FileResponse(static)

        try:
            await target(scope, capped_receive, secured_send)
        except _TooLarge:
            if not started:
                await _send_json(send, 413, {"detail": "request body too large"})


def _static_file(path: str) -> Path | None:
    """Serve the built SPA (frontend/dist) from the API origin; unknown paths fall back to index.html."""
    if not DIST.is_dir():
        return None
    candidate = (DIST / path.lstrip("/")).resolve()
    if candidate.is_file() and candidate.is_relative_to(DIST):
        return candidate
    index = DIST / "index.html"
    return index if index.is_file() else None


def install(app):
    app.add_middleware(SecurityMiddleware)

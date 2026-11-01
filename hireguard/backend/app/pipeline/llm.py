"""Model transport: Ollama (round-robin over HG_OLLAMA_HOSTS, local or a Modal endpoint behind proxy auth),
optional Groq fallback (fictional data only). One retry on 502/503/504 or a timeout (Modal cold start).

No tools, no memory, no conversation: one system prompt + one data block per call, JSON-schema output.
"""
from __future__ import annotations

import itertools
import json
import logging
import ssl
import sys
import threading
import time

import httpx

from .. import config

log = logging.getLogger("hireguard.llm")

_rr = itertools.cycle(range(max(len(config.OLLAMA_URLS), 1)))
_rr_lock = threading.Lock()
TIMEOUT = httpx.Timeout(config.LLM_TIMEOUT, connect=5.0)
RETRY_STATUS = (502, 503, 504)  # a Modal cold start answers 502/503 or times out for 1-3 minutes


class LLMUnavailable(Exception):
    pass


def _tls_context() -> ssl.SSLContext:
    """Verified TLS that also trusts the operating system's certificate store on Windows. Antivirus and company
    proxies re-sign HTTPS with a root certificate that Windows trusts but Python's bundled list does not, which
    makes every call to a cloud API fail with CERTIFICATE_VERIFY_FAILED. Verification stays ON."""
    ctx = ssl.create_default_context()
    if sys.platform == "win32":
        for store in ("ROOT", "CA"):
            try:
                for cert, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        try:
                            ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(cert))
                        except ssl.SSLError:
                            pass  # an expired or malformed system certificate is skipped, not fatal
            except OSError:
                pass
    return ctx


TLS = _tls_context()


def _next_url() -> str:
    with _rr_lock:
        return config.OLLAMA_URLS[next(_rr)]


def _auth_headers() -> dict:
    """Modal proxy auth, only when both values are set. Never logged."""
    if config.OLLAMA_MODAL_KEY and config.OLLAMA_MODAL_SECRET:
        return {"Modal-Key": config.OLLAMA_MODAL_KEY, "Modal-Secret": config.OLLAMA_MODAL_SECRET}
    return {}


def _scrub(msg: str) -> str:
    for secret in (config.OLLAMA_MODAL_KEY, config.OLLAMA_MODAL_SECRET, config.GROQ_API_KEY, config.GEMINI_API_KEY):
        if secret:
            msg = msg.replace(secret, "***")
    return msg


def _ollama(system: str, user: str, schema: dict) -> str:
    url = _next_url()
    body = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
    }
    for attempt in (1, 2):
        try:
            r = httpx.post(f"{url}/api/chat", json=body, timeout=TIMEOUT, headers=_auth_headers())
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            retryable = isinstance(e, httpx.TimeoutException) or e.response.status_code in RETRY_STATUS
            if attempt == 1 and retryable:
                log.warning("ollama %s: %s, retrying once", url, type(e).__name__)
                continue
            raise LLMUnavailable(_scrub(f"ollama {url}: {e}")) from None
        except httpx.HTTPError as e:
            raise LLMUnavailable(_scrub(f"ollama {url}: {e}")) from None


def _groq(system: str, user: str, schema: dict) -> str:
    if not config.GROQ_API_KEY:
        raise LLMUnavailable("groq fallback enabled but GROQ_API_KEY missing")
    body = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "system", "content": system + "\nReturn JSON matching this schema:\n" + json.dumps(schema)},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMUnavailable(_scrub(f"groq: {e}")) from None
    return r.json()["choices"][0]["message"]["content"]


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_RATE_WAIT_S = 8.0       # pause after a 429 when Google gives no Retry-After
GEMINI_RATE_WAIT_MAX_S = 30.0  # never block a request longer than this


def _gemini(system: str, user: str, schema: dict) -> str:
    """Google Gemini. The key goes in a header, never in the URL, so it cannot end up in a log line.
    The schema is given in the prompt (the same JSON the validator checks afterwards): the model's output is
    never trusted, whichever provider produced it."""
    if not config.GEMINI_API_KEY:
        raise LLMUnavailable("HG_LLM_PROVIDER=gemini but GEMINI_API_KEY is missing")
    body = {
        "systemInstruction": {"parts": [{"text": system + "\nReturn only JSON matching this schema:\n" + json.dumps(schema)}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    last: LLMUnavailable | None = None
    for model in config.GEMINI_MODELS or [config.GEMINI_MODEL]:
        try:
            return _gemini_one(model, body)
        except _QuotaExhausted as e:
            last = LLMUnavailable(str(e))
            log.warning("gemini: quota used up for %s, trying the next model", model)
    raise last or LLMUnavailable("gemini: no model configured")


class _QuotaExhausted(LLMUnavailable):
    pass


def _gemini_one(model: str, body: dict) -> str:
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    for attempt in (1, 2):
        try:
            r = httpx.post(url, json=body, timeout=TIMEOUT, verify=TLS, headers={"x-goog-api-key": config.GEMINI_API_KEY})
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 429 and "per day" in (e.response.text or ""):
                raise _QuotaExhausted(f"gemini: daily quota used up for {model}") from None
            retryable = isinstance(e, httpx.TimeoutException) or code in (429, 500, 502, 503, 504)
            if attempt == 1 and retryable:
                # a rate limit (429) needs a pause, not an immediate second try
                wait = 0.0
                if code == 429:
                    try:
                        wait = float(e.response.headers.get("retry-after", GEMINI_RATE_WAIT_S))
                    except (TypeError, ValueError):
                        wait = GEMINI_RATE_WAIT_S
                log.warning("gemini: %s, retrying once%s", type(e).__name__, f" after {wait:.0f}s" if wait else "")
                time.sleep(min(wait, GEMINI_RATE_WAIT_MAX_S))
                continue
            raise LLMUnavailable(_scrub(f"gemini: {type(e).__name__}{f' {code}' if code else ''}")) from None
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMUnavailable(_scrub(f"gemini: {type(e).__name__}")) from None
    raise LLMUnavailable("gemini: no answer")


def complete_json(system: str, user: str, schema: dict) -> dict:
    """Returns parsed JSON (not yet validated). Raises LLMUnavailable or ValueError."""
    if config.LLM_PROVIDER == "gemini":
        return json.loads(_gemini(system, user, schema))
    try:
        raw = _ollama(system, user, schema)
    except LLMUnavailable as e:
        if not config.GROQ_FALLBACK:
            raise
        log.warning("ollama unavailable (%s), using Groq fallback: fictional data only", e)
        raw = _groq(system, user, schema)
    return json.loads(raw)


# ---------------------------------------------------------------- reachability (GET /model/status)

STATUS_FLOOR_S = 10  # even refresh=1 reuses a result this fresh
STATUS_TTL_S = 60  # each check can wake a scaled-to-zero Modal GPU: cache it so page views don't keep it warm
_status_cache: tuple[float, dict] | None = None


def has_model(names: set[str], model: str | None = None) -> bool:
    """True if Ollama's /api/tags names include the configured model ("qwen3:8b", or "qwen3" -> any tag)."""
    model = model or config.OLLAMA_MODEL
    base = model.split(":")[0]
    return any(n.split(":")[0] == base and (":" not in model or n in (model, model + ":latest")) for n in names)


def _host_kind(url: str) -> str:
    if ".modal.run" in url:
        return "modal"
    return "local" if any(h in url for h in ("://localhost", "://127.0.0.1", "://[::1]")) else "remote"


def status(force: bool = False) -> dict:
    """Can the backend reach the model? Never returns the host URL or credentials, only their kind."""
    global _status_cache
    now = time.monotonic()
    if _status_cache and now - _status_cache[0] < (STATUS_FLOOR_S if force else STATUS_TTL_S):
        return _status_cache[1] | {"cached": True}
    if config.LLM_PROVIDER == "gemini":
        return _gemini_status(now)
    url = config.OLLAMA_URLS[0]
    kind = _host_kind(url)
    out = {"model": config.OLLAMA_MODEL, "host": kind, "hosts": len(config.OLLAMA_URLS),
           "credentials": bool(_auth_headers()), "groq_fallback": config.GROQ_FALLBACK,
           "reachable": False, "model_loaded": False, "latency_ms": None, "error": None, "cached": False}
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{url}/api/tags", timeout=httpx.Timeout(8.0, connect=4.0), headers=_auth_headers())
        out["latency_ms"] = round(1000 * (time.monotonic() - t0))
        if r.status_code in (401, 403):
            out["error"] = ("the Modal endpoint refused the backend: set HG_OLLAMA_MODAL_KEY and HG_OLLAMA_MODAL_SECRET"
                            " in .env.modal" if kind == "modal" else f"the model host refused the request ({r.status_code})")
        else:
            r.raise_for_status()
            out["reachable"] = True
            out["model_loaded"] = has_model({m.get("name", "") for m in r.json().get("models", [])})
            if not out["model_loaded"]:
                out["error"] = f"{config.OLLAMA_MODEL} is not pulled on the model host"
    except httpx.TimeoutException:
        out["error"] = ("no answer within 8 s: a Modal cold start takes 1-3 minutes, check again shortly"
                        if kind == "modal" else "no answer within 8 s")
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = _scrub(f"{type(e).__name__}: model host unreachable")
    _status_cache = (now, out)
    return out


def _gemini_status(now: float) -> dict:
    """Reachability for the Gemini provider: lists the model (no tokens used)."""
    global _status_cache
    out = {"model": config.GEMINI_MODEL, "host": "gemini", "hosts": 1, "credentials": bool(config.GEMINI_API_KEY),
           "groq_fallback": False, "reachable": False, "model_loaded": False, "latency_ms": None, "error": None,
           "cached": False}
    if not config.GEMINI_API_KEY:
        out["error"] = "GEMINI_API_KEY is not set on the backend"
    else:
        t0 = time.monotonic()
        try:
            r = httpx.get(f"{GEMINI_BASE}/models/{config.GEMINI_MODEL}", timeout=httpx.Timeout(8.0, connect=4.0), verify=TLS,
                          headers={"x-goog-api-key": config.GEMINI_API_KEY})
            out["latency_ms"] = round(1000 * (time.monotonic() - t0))
            if r.status_code in (400, 401, 403):
                out["error"] = "Google refused the API key: check GEMINI_API_KEY"
            elif r.status_code == 404:
                out["reachable"] = True
                out["error"] = f"Google does not know the model {config.GEMINI_MODEL}: check HG_GEMINI_MODEL"
            else:
                r.raise_for_status()
                out["reachable"] = out["model_loaded"] = True
        except httpx.TimeoutException:
            out["error"] = "Google did not answer within 8 s"
        except httpx.HTTPError as e:
            out["error"] = _scrub(f"{type(e).__name__}: Google API unreachable")
    _status_cache = (now, out)
    return out

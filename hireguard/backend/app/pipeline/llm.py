"""Model transport: Ollama (round-robin over HG_OLLAMA_HOSTS, local or a Modal endpoint behind proxy auth),
optional Groq fallback (fictional data only). One retry on 502/503/504 or a timeout (Modal cold start).

No tools, no memory, no conversation: one system prompt + one data block per call, JSON-schema output.
"""
from __future__ import annotations

import itertools
import json
import logging
import threading

import httpx

from .. import config

log = logging.getLogger("hireguard.llm")

_rr = itertools.cycle(range(max(len(config.OLLAMA_URLS), 1)))
_rr_lock = threading.Lock()
TIMEOUT = httpx.Timeout(config.LLM_TIMEOUT, connect=5.0)
RETRY_STATUS = (502, 503, 504)  # a Modal cold start answers 502/503 or times out for 1-3 minutes


class LLMUnavailable(Exception):
    pass


def _next_url() -> str:
    with _rr_lock:
        return config.OLLAMA_URLS[next(_rr)]


def _auth_headers() -> dict:
    """Modal proxy auth, only when both values are set. Never logged."""
    if config.OLLAMA_MODAL_KEY and config.OLLAMA_MODAL_SECRET:
        return {"Modal-Key": config.OLLAMA_MODAL_KEY, "Modal-Secret": config.OLLAMA_MODAL_SECRET}
    return {}


def _scrub(msg: str) -> str:
    for secret in (config.OLLAMA_MODAL_KEY, config.OLLAMA_MODAL_SECRET, config.GROQ_API_KEY):
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


def complete_json(system: str, user: str, schema: dict) -> dict:
    """Returns parsed JSON (not yet validated). Raises LLMUnavailable or ValueError."""
    try:
        raw = _ollama(system, user, schema)
    except LLMUnavailable as e:
        if not config.GROQ_FALLBACK:
            raise
        log.warning("ollama unavailable (%s), using Groq fallback: fictional data only", e)
        raw = _groq(system, user, schema)
    return json.loads(raw)

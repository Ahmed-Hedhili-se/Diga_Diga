"""Model transport: Ollama (round-robin over HG_OLLAMA_URLS), optional Groq fallback (fictional data only).

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
TIMEOUT = httpx.Timeout(120.0, connect=5.0)


class LLMUnavailable(Exception):
    pass


def _next_url() -> str:
    with _rr_lock:
        return config.OLLAMA_URLS[next(_rr)]


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
    try:
        r = httpx.post(f"{url}/api/chat", json=body, timeout=TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"ollama {url}: {e}") from e
    return r.json()["message"]["content"]


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
        raise LLMUnavailable(f"groq: {e}") from e
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

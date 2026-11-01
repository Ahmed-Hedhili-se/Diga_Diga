"""Remote Ollama transport (T7.2): Modal proxy-auth headers, secret hygiene, one retry, Groq flag. No network."""
import importlib
import logging

import httpx
import pytest

from app import config
from app.pipeline import llm

KEY, SECRET = "wk-test-key-123", "ws-test-secret-456"
OK_BODY = {"message": {"content": '{"language": "fr", "intent": "other", "urgency": "low"}'}}


class FakePost:
    """Replays a script of outcomes: a dict = 200 JSON body, an int = that HTTP status, 'timeout' = ReadTimeout."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        out = self.script.pop(0) if self.script else self.script_last
        self.script_last = out
        req = httpx.Request("POST", url)
        if out == "timeout":
            raise httpx.ReadTimeout("timed out", request=req)
        if isinstance(out, int):
            return httpx.Response(out, request=req, text=f"error {out} for key {KEY}")
        return httpx.Response(200, request=req, json=out)


@pytest.fixture()
def remote(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URLS", ["https://hg--ollama.modal.run"])
    monkeypatch.setattr(llm, "_rr", iter([0] * 100))
    monkeypatch.setattr(config, "GROQ_FALLBACK", False)

    def install(*script, key="", secret=""):
        monkeypatch.setattr(config, "OLLAMA_MODAL_KEY", key)
        monkeypatch.setattr(config, "OLLAMA_MODAL_SECRET", secret)
        fake = FakePost(*script)
        monkeypatch.setattr(llm.httpx, "post", fake)
        return fake
    return install


def test_modal_headers_sent_only_when_both_set(remote):
    fake = remote(OK_BODY, key=KEY, secret=SECRET)
    assert llm.complete_json("s", "u", {})["intent"] == "other"
    assert fake.calls[0]["headers"] == {"Modal-Key": KEY, "Modal-Secret": SECRET}
    fake = remote(OK_BODY)
    llm.complete_json("s", "u", {})
    assert "Modal-Key" not in fake.calls[0]["headers"] and "Modal-Secret" not in fake.calls[0]["headers"]
    fake = remote(OK_BODY, key=KEY, secret="")  # half-configured: send nothing rather than a partial credential
    llm.complete_json("s", "u", {})
    assert fake.calls[0]["headers"] == {}


def test_secret_never_in_logs_or_errors(remote, caplog):
    caplog.set_level(logging.DEBUG)
    remote(503, 401, key=KEY, secret=SECRET)  # 503 is retried, 401 is final; the 401 body echoes the key
    with pytest.raises(llm.LLMUnavailable) as e:
        llm.complete_json("s", "u", {})
    for text in (str(e.value), caplog.text):
        assert KEY not in text and SECRET not in text


def test_cold_start_is_retried_once_then_succeeds(remote):
    fake = remote(503, OK_BODY)
    assert llm.complete_json("s", "u", {})["urgency"] == "low"
    assert len(fake.calls) == 2


def test_timeout_retried_once_then_needs_human(remote):
    from app.pipeline.email_extract import extract_email
    fake = remote("timeout", "timeout", "timeout", "timeout")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("s", "u", {})
    assert len(fake.calls) == 2  # one retry, not more
    fake.calls.clear()
    assert extract_email("Bonjour, je voudrais des nouvelles de ma candidature.") is None  # -> needs_human
    assert len(fake.calls) == 4  # extractor's own 2 attempts x transport's 2 tries, then it gives up


def test_client_errors_are_not_retried(remote):
    fake = remote(400)
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("s", "u", {})
    assert len(fake.calls) == 1


def test_groq_flag_off_means_no_groq_request(remote, monkeypatch):
    fake = remote(503, 503)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk-should-not-be-used")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("s", "u", {})
    assert not any("groq" in c["url"] for c in fake.calls)


def test_groq_flag_on_falls_back_once(remote, monkeypatch):
    groq_body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    fake = remote(503, 503, groq_body)
    monkeypatch.setattr(config, "GROQ_FALLBACK", True)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk-fictional-only")
    assert llm.complete_json("s", "u", {}) == {"ok": True}
    assert [("groq" in c["url"]) for c in fake.calls] == [False, False, True]


def test_hosts_env_preferred_over_urls(monkeypatch):
    try:
        monkeypatch.setenv("HG_OLLAMA_URLS", "http://old:11434")
        monkeypatch.setenv("HG_OLLAMA_HOSTS", "https://a.modal.run/, http://b:11434")
        importlib.reload(config)
        assert config.OLLAMA_URLS == ["https://a.modal.run", "http://b:11434"]
        monkeypatch.delenv("HG_OLLAMA_HOSTS")
        importlib.reload(config)
        assert config.OLLAMA_URLS == ["http://old:11434"]
    finally:
        monkeypatch.undo()
        importlib.reload(config)


# ---------------------------------------------------------------- Modal 303 "resume" for requests over 150 s

class FakeGet:
    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, url, timeout=None, headers=None):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        out = self.script.pop(0)
        req = httpx.Request("GET", url)
        if out == "resume":
            return httpx.Response(303, request=req, headers={"location": f"{url}?__modal_attempt_token=t2"})
        return httpx.Response(200, request=req, json=out)


def _resume_redirect(location: str):
    return httpx.Response(303, request=httpx.Request("POST", "https://gpu.example/api/chat"),
                          headers={"location": location})


def test_modal_303_resume_is_followed_on_the_same_host(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URLS", ["https://gpu.example"])
    monkeypatch.setattr(config, "OLLAMA_MODAL_KEY", KEY)
    monkeypatch.setattr(config, "OLLAMA_MODAL_SECRET", SECRET)
    monkeypatch.setattr(llm.httpx, "post", lambda url, json=None, timeout=None, headers=None:
                        _resume_redirect("https://gpu.example/api/chat?__modal_attempt_token=t1"))
    get = FakeGet("resume", OK_BODY)
    monkeypatch.setattr(llm.httpx, "get", get)
    out = llm._ollama("s", "u", {})
    assert '"intent": "other"' in out
    assert len(get.calls) == 2 and all(c["headers"].get("Modal-Key") == KEY for c in get.calls)


def test_a_303_to_another_host_is_refused_and_gets_no_credentials(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URLS", ["https://gpu.example"])
    monkeypatch.setattr(config, "OLLAMA_MODAL_KEY", KEY)
    monkeypatch.setattr(config, "OLLAMA_MODAL_SECRET", SECRET)
    monkeypatch.setattr(llm.httpx, "post", lambda url, json=None, timeout=None, headers=None:
                        _resume_redirect("https://evil.example/collect"))
    get = FakeGet(OK_BODY)
    monkeypatch.setattr(llm.httpx, "get", get)
    with pytest.raises(llm.LLMUnavailable) as e:
        llm._ollama("s", "u", {})
    assert get.calls == []                                   # nothing was sent to the other host
    assert KEY not in str(e.value) and SECRET not in str(e.value)

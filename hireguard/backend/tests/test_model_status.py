"""GET /model/status: reports whether the backend can reach the model host, without leaking the URL or the
Modal proxy credentials, and without letting page views keep a scaled-to-zero GPU awake."""
import httpx
import pytest

from app import config
from app.contracts import Role
from app.pipeline import llm
from test_backend_contracts import client, db  # noqa: F401  (db is a fixture)

MODAL = "https://team--hireguard-ollama-ollama.us-east.modal.run"
KEY, SECRET = "wk-test-key-123", "ws-test-secret-456"


class _Resp:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("GET", MODAL), response=httpx.Response(self.status_code))


@pytest.fixture
def modal(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URLS", [MODAL])
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setattr(config, "OLLAMA_MODAL_KEY", KEY)
    monkeypatch.setattr(config, "OLLAMA_MODAL_SECRET", SECRET)
    monkeypatch.setattr(llm, "_status_cache", None)
    calls = []

    def use(resp):
        def fake_get(url, timeout=None, headers=None):
            calls.append(headers)
            if isinstance(resp, Exception):
                raise resp
            return resp
        monkeypatch.setattr(llm.httpx, "get", fake_get)
        return calls
    return use


def test_ready_model_on_modal(db, modal):
    calls = modal(_Resp(200, {"models": [{"name": "qwen3:8b"}]}))
    s = client(Role.recruiter).get("/api/model/status").json()
    assert s["reachable"] and s["model_loaded"] and s["host"] == "modal" and s["credentials"] and s["error"] is None
    assert calls[0] == {"Modal-Key": KEY, "Modal-Secret": SECRET}


def test_missing_credentials_is_explained_and_nothing_leaks(db, modal):
    modal(_Resp(401))
    r = client(Role.hr_manager).get("/api/model/status")
    s = r.json()
    assert not s["reachable"] and "HG_OLLAMA_MODAL_KEY" in s["error"]
    assert "modal.run" not in r.text and KEY not in r.text and SECRET not in r.text


def test_model_not_pulled_and_timeout(db, modal):
    modal(_Resp(200, {"models": [{"name": "llama3:8b"}]}))
    c = client(Role.admin)
    s = c.get("/api/model/status").json()
    assert s["reachable"] and not s["model_loaded"] and "qwen3:8b" in s["error"]
    llm._status_cache = None
    modal(httpx.ConnectTimeout("slow"))
    s = c.get("/api/model/status").json()
    assert not s["reachable"] and "cold start" in s["error"]


def test_cached_so_page_views_do_not_wake_the_gpu(db, modal):
    calls = modal(_Resp(200, {"models": [{"name": "qwen3:8b"}]}))
    c = client(Role.recruiter)
    first = c.get("/api/model/status").json()
    again = c.get("/api/model/status").json()
    forced = c.get("/api/model/status?refresh=1").json()  # within the 10 s floor: still cached
    assert len(calls) == 1 and not first["cached"] and again["cached"] and forced["cached"]


def test_employees_cannot_probe_the_model(db, modal):
    modal(_Resp(200))
    assert client(Role.employee).get("/api/model/status").status_code == 403


def test_has_model_tag_matching():
    assert llm.has_model({"qwen3:8b"}, "qwen3:8b")
    assert llm.has_model({"qwen3:latest"}, "qwen3")
    assert not llm.has_model({"qwen3:14b"}, "qwen3:8b")
    assert not llm.has_model({"qwen2.5:8b"}, "qwen3:8b")


# ---------------------------------------------------------------- Gemini provider

GKEY = "AIza-test-key-not-real-123"


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", GKEY)
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(llm, "_status_cache", None)
    seen = {}

    def use(resp):
        def fake(url, **kw):
            seen.update(url=url, headers=kw.get("headers"), json=kw.get("json"), verify=kw.get("verify"))
            if isinstance(resp, Exception):
                raise resp
            return resp
        monkeypatch.setattr(llm.httpx, "post", fake)
        monkeypatch.setattr(llm.httpx, "get", fake)
        return seen
    return use


def test_gemini_returns_parsed_json_and_keeps_the_key_out_of_the_url(gemini):
    seen = gemini(_Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"skills": []}'}]}}]}))
    assert llm.complete_json("sys", "user", {"type": "object"}) == {"skills": []}
    assert GKEY not in seen["url"] and seen["headers"] == {"x-goog-api-key": GKEY}
    assert seen["verify"] is llm.TLS  # certificate verification stays on
    assert "JSON" in seen["json"]["systemInstruction"]["parts"][0]["text"]


def test_gemini_failure_is_unavailable_and_never_leaks_the_key(gemini):
    gemini(httpx.ConnectError(f"boom {GKEY}"))
    with pytest.raises(llm.LLMUnavailable) as e:
        llm.complete_json("s", "u", {})
    assert GKEY not in str(e.value)


def test_gemini_status_reports_provider_without_secrets(db, gemini):
    gemini(_Resp(200))
    r = client(Role.recruiter).get("/api/model/status")
    s = r.json()
    assert s["host"] == "gemini" and s["reachable"] and s["model_loaded"] and s["credentials"]
    assert GKEY not in r.text and "googleapis" not in r.text


def test_gemini_status_explains_a_refused_key(db, gemini):
    gemini(_Resp(403))
    s = client(Role.recruiter).get("/api/model/status").json()
    assert not s["reachable"] and "GEMINI_API_KEY" in s["error"]

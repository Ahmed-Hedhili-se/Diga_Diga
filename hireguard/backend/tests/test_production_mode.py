"""Production mode refuses to start with an insecure configuration; HTTPS deployments send HSTS."""
import pytest

from app import config, hardening, security

SAFE = dict(cookie_secure=True, api_docs=False, cors_origins=["https://hr.example.tn"], llm_provider="ollama",
            groq_fallback=False, allow_cloud_llm=False, ollama_urls=["http://localhost:11434"],
            odoo_enabled=False, odoo_url="http://localhost:8069", parse_isolation=True)


def problems(**override):
    return hardening.production_problems(**(SAFE | override))


def test_a_safe_configuration_has_no_problems():
    assert problems() == []


@pytest.mark.parametrize("override,needle", [
    ({"cookie_secure": False}, "HG_COOKIE_SECURE"),
    ({"api_docs": True}, "HG_API_DOCS"),
    ({"cors_origins": ["http://hr.example.tn"]}, "HG_CORS_ORIGINS"),
    ({"cors_origins": []}, "HG_CORS_ORIGINS"),
    ({"llm_provider": "gemini"}, "HG_LLM_PROVIDER"),
    ({"groq_fallback": True}, "HG_GROQ_FALLBACK"),
    ({"ollama_urls": ["http://gpu.example.tn:11434"]}, "HG_OLLAMA_HOSTS"),
    ({"odoo_enabled": True, "odoo_url": "http://odoo.example.tn"}, "HG_ODOO_URL"),
    ({"parse_isolation": False}, "HG_PARSE_ISOLATION"),
])
def test_each_insecure_setting_is_reported(override, needle):
    assert any(needle in p for p in problems(**override))


def test_cloud_providers_need_an_explicit_acknowledgement():
    assert problems(llm_provider="gemini", allow_cloud_llm=True) == []
    assert problems(groq_fallback=True, allow_cloud_llm=True) == []


def test_local_http_is_fine_for_a_model_next_to_the_app():
    assert problems(ollama_urls=["http://127.0.0.1:11434"], odoo_enabled=True, odoo_url="http://localhost:8069") == []


def test_production_refuses_to_start_when_unsafe(monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    with pytest.raises(RuntimeError) as e:
        hardening.enforce()
    assert "HG_COOKIE_SECURE" in str(e.value)


def test_development_only_warns(monkeypatch, caplog):
    monkeypatch.setattr(config, "PRODUCTION", False)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    hardening.enforce()  # does not raise


def test_hsts_only_on_https_deployments():
    names = lambda h: {k for k, _ in h}  # noqa: E731
    assert b"strict-transport-security" in names(security.headers_for(True))
    assert b"strict-transport-security" not in names(security.headers_for(False))

"""Production mode: refuse to start with an insecure configuration.

Development stays easy (plain http, Swagger UI, any model provider). With HG_ENV=production every setting below
is checked at startup, and the server will not start while one is wrong, so a deployment cannot silently run
with the fail-open development defaults. Settings are passed in explicitly so the rules are testable.
"""
from __future__ import annotations

from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_local(url: str) -> bool:
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS


def production_problems(*, cookie_secure: bool, api_docs: bool, cors_origins: list[str], llm_provider: str,
                        groq_fallback: bool, allow_cloud_llm: bool, ollama_urls: list[str],
                        odoo_enabled: bool, odoo_url: str, parse_isolation: bool) -> list[str]:
    problems = []
    if not cookie_secure:
        problems.append("HG_COOKIE_SECURE must be 1 (session cookies only over HTTPS)")
    if api_docs:
        problems.append("HG_API_DOCS must be 0 (Swagger UI uses a relaxed CSP)")
    bad_origins = [o for o in cors_origins if urlsplit(o).scheme != "https"]
    if not cors_origins or bad_origins:
        problems.append("HG_CORS_ORIGINS must list https origins only" + (f" (found {bad_origins})" if bad_origins else ""))
    if not allow_cloud_llm and llm_provider != "ollama":
        problems.append(f"HG_LLM_PROVIDER={llm_provider} sends CV text to a cloud service: set HG_ALLOW_CLOUD_LLM=1 "
                        "only with fictional or consented data")
    if not allow_cloud_llm and groq_fallback:
        problems.append("HG_GROQ_FALLBACK=1 sends CV text to a cloud service: set HG_ALLOW_CLOUD_LLM=1 only with "
                        "fictional or consented data")
    plain = [u for u in ollama_urls if urlsplit(u).scheme != "https" and not _is_local(u)]
    if plain:
        problems.append(f"HG_OLLAMA_HOSTS has a remote host without https: {plain}")
    if not parse_isolation:
        problems.append("HG_PARSE_ISOLATION must be 1 (uploaded PDFs are parsed in a separate, time-limited process)")
    if odoo_enabled and urlsplit(odoo_url).scheme != "https" and not _is_local(odoo_url):
        problems.append("HG_ODOO_URL must be https when the Odoo connector is enabled")
    return problems


def enforce() -> None:
    """Called at startup. Raises in production when anything is insecure; development only logs a hint."""
    import logging

    from . import config
    from .erp import odoo_client

    problems = production_problems(
        cookie_secure=config.COOKIE_SECURE, api_docs=config.API_DOCS, cors_origins=config.CORS_ORIGINS,
        llm_provider=config.LLM_PROVIDER, groq_fallback=config.GROQ_FALLBACK, allow_cloud_llm=config.ALLOW_CLOUD_LLM,
        ollama_urls=config.OLLAMA_URLS, odoo_enabled=odoo_client.ENABLED, odoo_url=odoo_client.URL,
        parse_isolation=config.PARSE_ISOLATION)
    log = logging.getLogger("hireguard")
    if config.PRODUCTION:
        if problems:
            raise RuntimeError("HG_ENV=production but the configuration is not safe:\n  - " + "\n  - ".join(problems))
        log.info("production mode: configuration checked")
    elif problems:
        log.warning("development configuration. Before real data set HG_ENV=production, which refuses to start with: %s",
                    "; ".join(problems))

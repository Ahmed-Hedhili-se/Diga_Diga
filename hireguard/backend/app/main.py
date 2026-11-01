"""HireGuard API. Each layer exposes `router` in its own routes.py; prefixes are frozen in contracts/API.md."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import API_DOCS, CORS_ORIGINS, COOKIE_SECURE
from .db import init_db
from .auth import routes as auth_routes            # P4
from .pipeline import routes as pipeline_routes    # P1
from .scoring import routes as scoring_routes      # P2
from .workflow import routes as workflow_routes    # P3
from .erp import routes as erp_routes              # Odoo connector (off unless HG_ODOO_ENABLED=1)
from .team import routes as team_routes            # HR Nexus (Team module)
from .agent import routes as agent_routes          # propose-only planning agent
from . import hardening, security                  # P4: headers, CSP, rate limits; production-mode checks

if API_DOCS and COOKIE_SECURE:  # HG_COOKIE_SECURE=1 means HTTPS, i.e. a real deployment
    logging.getLogger("hireguard").warning(
        "HG_API_DOCS=1 on a deployment with secure cookies: /api/docs and its relaxed CSP are exposed. Set HG_API_DOCS=0.")

# Swagger UI needs a relaxed CSP (pentest O1): HG_API_DOCS=0 turns it off in production.
app = FastAPI(title="Venidis", docs_url="/api/docs" if API_DOCS else None, redoc_url=None,
              openapi_url="/api/openapi.json" if API_DOCS else None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
security.install(app)

app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
app.include_router(pipeline_routes.router, prefix="/api", tags=["pipeline"])
app.include_router(scoring_routes.router, prefix="/api", tags=["scoring"])
app.include_router(workflow_routes.router, prefix="/api", tags=["workflow"])
app.include_router(erp_routes.router, prefix="/api", tags=["erp"])
app.include_router(team_routes.router, prefix="/api", tags=["team"])
app.include_router(agent_routes.router, prefix="/api", tags=["agent"])


@app.on_event("startup")
def _startup():
    hardening.enforce()  # production mode: refuse to start with an insecure configuration
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}

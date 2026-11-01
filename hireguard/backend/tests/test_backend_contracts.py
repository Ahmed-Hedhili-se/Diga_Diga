"""Backend contract tests (persons/rayen.md): docs, frontend consumers and schemas agree with the code, the response
shapes the UI relies on hold, and scoring inputs are validated and audited server-side."""
import json
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import db as app_db
from app import security
from app.auth import core as auth
from app.config import ROOT
from app.contracts import ApprovalKind, EmailExtraction, Role
from app.export_schemas import MODELS
from app.main import app
from app.pipeline import demo as pipeline_demo
from app.workflow import approvals, audit, demo as workflow_demo, email_gate
from test_workflow import make_user

API_MD = ROOT / "contracts" / "API.md"
FRONTEND = ROOT / "frontend" / "src"


def _norm(path: str) -> str:
    """'/api/jobs/{job_id}/rubric?x=1' and '/jobs/${encodeURIComponent(id)}/rubric' -> '/jobs/{}/rubric'."""
    path = path.split("?")[0].removeprefix("/api")
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/") or "/"


def _live_routes() -> set[tuple[str, str]]:
    return {(m, _norm(r.path)) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    security.limiter.reset()
    app_db.init_db()
    return tmp_path


def client(role: Role, uid: str | None = None) -> TestClient:
    user = make_user(role, uid or f"u-{role.value}")
    c = TestClient(app)
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return c

# ---------------------------------------------------------------- docs, frontend and schemas vs code


def test_every_route_is_documented_in_api_md():
    documented = set()
    for m, path in re.findall(r"^\| ([A-Z/]+) \| `([^`]+)`", API_MD.read_text(encoding="utf-8"), re.M):
        documented |= {(x, _norm(path)) for x in m.split("/")}
    missing = sorted(_live_routes() - documented)
    stale = sorted(documented - _live_routes())
    assert not missing, f"implemented but not in contracts/API.md: {missing}"
    assert not stale, f"documented in contracts/API.md but not implemented: {stale}"


def test_frontend_only_calls_routes_that_exist():
    paths = {p for m, p in _live_routes()}
    src = "\n".join(f.read_text(encoding="utf-8") for f in FRONTEND.rglob("*.ts*"))
    # first argument of api(...), apiBlob(...), downloadFile(...)
    called = {_norm(p) for p in re.findall(r"(?:api|apiBlob|downloadFile)(?:<[^>(]*>)?\(\s*[`\"'](/[^`\"']*)", src)}
    assert len(called) > 30
    unknown = sorted(c for c in called if c not in paths)
    assert not unknown, f"frontend calls routes the backend does not have: {unknown}"


def test_exported_json_schemas_match_the_models():
    stale = [name for name, model in MODELS.items()
             if json.loads((ROOT / "contracts" / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
             != json.loads(json.dumps(model.model_json_schema()))]
    assert not stale, f"run `python -m app.export_schemas`: stale schemas {stale}"

# ---------------------------------------------------------------- response shapes the UI depends on (types.ts)


def test_session_shape(db):
    me = client(Role.hr_manager).get("/api/auth/me").json()
    assert set(me) == {"user", "role", "permissions", "csrf", "idle_timeout_s"}
    assert set(me["user"]) == {"id", "email", "display_name", "role"}


def test_candidate_detail_shape(db):
    pipeline_demo.seed_candidates(mode="ground_truth")
    c = client(Role.recruiter)
    row = c.get("/api/candidates?job_id=JOB-DATA-01").json()[0]
    assert {"candidate_id", "name", "email", "job_id", "status", "score", "flags", "hidden"} <= set(row)
    d = c.get("/api/candidates/CAND-006").json()
    assert {"validated", "page_count", "hidden_findings"} <= set(d)
    assert all({"channel", "text", "page", "bbox", "severity"} <= set(f) for f in d["hidden_findings"])
    assert all({"esco_id", "label", "evidence", "years", "support"} <= set(s) for s in d["validated"]["skills"])
    assert "skills_listed_only_ratio" in d["validated"]
    assert {"start", "end"} == set(d["validated"]["skills"][0]["evidence"])


def test_inbox_and_approvals_shapes(db, monkeypatch):
    monkeypatch.setattr(email_gate, "_extract",
                        lambda body: EmailExtraction(language="fr", intent="status_question", urgency="normal"))
    fixtures = {f["id"]: f for f in workflow_demo.build_fixtures()}
    email_gate.ingest(fixtures["EML-011"]["raw"], inbox_id="EML-011")  # spoofed -> suspicious lane
    hrm = client(Role.hr_manager)
    lanes = hrm.get("/api/inbox").json()["lanes"]
    assert set(lanes) == {"routine", "needs_human", "suspicious"}
    group = lanes["suspicious"][0]
    assert {"intent", "urgency", "count", "items"} <= set(group)
    assert {"id", "from", "subject", "auth", "lane", "reasons", "status", "candidate_id", "draft_item_ids"} <= set(group["items"][0])

    approvals.create_item(ApprovalKind.email_send, "m", {"to": "a@b.example", "recipient_verified": True},
                          created_by="system")
    q = hrm.get("/api/approvals").json()
    assert set(q) == {"batches", "high_risk", "max_batch_size"}
    item = q["batches"][0]["items"][0]
    assert {"id", "kind", "risk", "risk_level", "status", "decisions", "required_approvals", "payload", "diff"} <= set(item)


def test_eval_summary_is_explicit_about_what_was_measured(db):
    s = client(Role.hr_manager).get("/api/eval/summary").json()
    if s.get("status") == "not_run":
        return
    for name, section in s["sections"].items():
        assert isinstance(section, dict) and section, name  # a section is either measured or says why it is skipped

# ---------------------------------------------------------------- scoring: validation, status, audit


def _rubric(c) -> dict:
    return c.get("/api/jobs/JOB-DATA-01/rubric").json()


@pytest.mark.parametrize("mutate,why", [
    (lambda r: r["skill_weights"].update(python=float("nan")), "finite"),
    (lambda r: r["skill_weights"].update(python=float("inf")), "finite"),
    (lambda r: r["component_weights"].update(skills=-5), "between"),
    (lambda r: r["component_weights"].update(charisma=10), "unknown score components"),
    (lambda r: r.update(component_weights={"skills": 0, "experience": 0, "degree": 0, "languages": 0}), "all be zero"),
    (lambda r: r["skill_weights"].update({"ignore-previous-instructions": 5}), "unknown skills"),
    (lambda r: r.update(skill_weights={}), "1 to"),
    (lambda r: r.update(min_years=500), "at most 60"),
    (lambda r: r.update(languages=[{"iso": "fr", "min_cefr": "B2"}, {"iso": "fr", "min_cefr": "C1"}]), "once"),
], ids=["nan", "inf", "negative", "unknown-component", "all-zero", "unknown-skill", "no-skills", "huge-years", "dup-lang"])
def test_hostile_rubrics_are_rejected_and_nothing_is_stored(db, mutate, why):
    hrm = client(Role.hr_manager)
    before = _rubric(hrm)
    bad = json.loads(json.dumps(before))
    mutate(bad)
    r = hrm.put("/api/jobs/JOB-DATA-01/rubric", content=json.dumps(bad), headers={"content-type": "application/json"})
    assert r.status_code == 400 and why in r.text, r.text
    assert _rubric(hrm) == before


def test_rubric_update_and_rescore_are_audited_and_scores_stay_proposed(db):
    pipeline_demo.seed_candidates(mode="ground_truth")
    hrm = client(Role.hr_manager)
    r = _rubric(hrm)
    r["skill_weights"]["python"] = 9
    assert hrm.put("/api/jobs/JOB-DATA-01/rubric", json=r).status_code == 200
    scores = hrm.post("/api/jobs/JOB-DATA-01/rescore").json()
    assert scores and all(s["status"] == "proposed" for s in scores)
    actions = {e.action for e in audit.list_entries(50)}
    assert {"rubric.update", "scores.rescore"} <= actions
    assert hrm.put("/api/jobs/JOB-DATA-01/rubric", json=r | {"job_id": "JOB-FS-02"}).status_code == 400
    assert hrm.put("/api/jobs/JOB-NOPE-99/rubric", json=r).status_code == 404
    assert audit.verify()["ok"]


def test_eval_report_states_mode_samples_and_limits(db, tmp_path, monkeypatch):
    from app.scoring import routes as scoring_routes
    rate = {"k": 2, "n": 40, "rate": 0.05, "ci95": [0.006, 0.17], "text": "2/40"}
    fake = {"model": "qwen3:8b", "generated_at": "2026-11-01T00:00:00+00:00", "groq_fallback": False, "sections": {
        "attacks": {"attack_success": rate, "llm_calls_total": 80, "limit": None},
        "twins": {"score_changed": rate | {"n": 12}, "llm_calls_total": 0, "limit": 12},
        "extraction": {"skipped": "no PDFs; run eval/gen_cvs.py"}}}
    f = tmp_path / "summary.json"
    f.write_text(json.dumps(fake), encoding="utf-8")
    monkeypatch.setattr(scoring_routes, "EVAL_SUMMARY", f)
    rep = client(Role.admin).get("/api/eval/summary").json()["report"]
    assert rep["sections"]["attacks"] == {"measured": True, "mode": "model", "samples": 40, "limit": None,
                                          "llm_calls": 80, "seconds": None}
    assert rep["sections"]["twins"]["mode"] == "code_path" and rep["sections"]["twins"]["samples"] == 12
    assert rep["sections"]["extraction"] == {"measured": False, "reason": "no PDFs; run eval/gen_cvs.py"}
    assert any("synthetic" in x for x in rep["limitations"])

    f.write_text("{broken", encoding="utf-8")
    assert client(Role.hr_manager, "hrm-2").get("/api/eval/summary").status_code == 500

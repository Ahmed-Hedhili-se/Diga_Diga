"""Trust analytics: shortlist stability (U1), team-aware rubric (team gaps), reviewer attention guard (U3)."""
import pytest

from app import db as app_db
from app.contracts import ApprovalKind, DegreeLevel, ExtractedLanguage, Role, Span, ValidatedCV, ValidSkill
from app.scoring import jobs
from app.scoring.stability import stability
from app.scoring.team_gaps import coverage, load_teams, suggest, team_gaps
from app.workflow import approvals, attention

from test_workflow import client_for, make_user


def cv(cid, skills, years=3.0):
    return ValidatedCV(
        candidate_id=cid, doc_id="d", status="ok",
        skills=[ValidSkill(esco_id=s, label=s, evidence=Span(start=0, end=3), page=0, years=y) for s, y in skills],
        years_experience=years, highest_degree=DegreeLevel.ingenieur, degree_evidence=Span(start=0, end=3),
        languages=[ExtractedLanguage(iso="fr", cefr="C1"), ExtractedLanguage(iso="en", cefr="B2")])


# ---------------------------------------------------------------- U1 stability

def test_clear_leader_is_stable_and_empty_cv_is_out():
    rubric = jobs.file_rubric("JOB-DATA-01")
    strong = cv("CAND-A", [(s, 4.0) for s in rubric.skill_weights])
    weak = cv("CAND-B", [], years=0.0)
    out = {r["candidate_id"]: r for r in stability([weak, strong], rubric, k=1, draws=100)}
    assert out["CAND-A"]["label"] == "stable_in" and out["CAND-A"]["p_top_k"] == 1.0
    assert out["CAND-B"]["label"] == "stable_out"


def test_near_tie_at_the_cutoff_is_borderline():
    rubric = jobs.file_rubric("JOB-DATA-01")  # python and sql both weigh 5: a tie only jitter can break
    a, b = cv("CAND-PY", [("python", 3.0)]), cv("CAND-SQL", [("sql", 3.0)])
    out = stability([a, b], rubric, k=1, draws=300)
    assert {r["label"] for r in out} == {"borderline"}
    assert abs(out[0]["p_top_k"] + out[1]["p_top_k"] - 1.0) < 1e-9


def test_exact_tie_at_the_cutoff_is_borderline_not_decided_by_id():
    rubric = jobs.file_rubric("JOB-DATA-01")
    twins = [cv("CAND-A", [("python", 3.0)]), cv("CAND-B", [("python", 3.0)])]  # identical profiles
    out = {r["candidate_id"]: r for r in stability(twins, rubric, k=1, draws=300)}
    assert out["CAND-A"]["base_rank"] == 1  # the displayed order is still deterministic
    assert out["CAND-A"]["label"] == out["CAND-B"]["label"] == "borderline"


def test_stability_is_deterministic():
    rubric = jobs.file_rubric("JOB-DATA-01")
    cvs = [cv(f"CAND-{i}", [("python", float(i)), ("sql", 4.0 - i)]) for i in range(5)]
    assert stability(cvs, rubric, k=2) == stability(cvs, rubric, k=2)


# ---------------------------------------------------------------- team-aware rubric

def test_team_gaps_follow_the_published_rules():
    team = load_teams()["JOB-DATA-01"]
    status = {c["esco_id"]: c["status"] for c in coverage(team)}
    assert status["apache-spark"] == "gap" and status["etl"] == "single_holder" and status["python"] == "covered"

    proposed, diff = suggest(jobs.file_rubric("JOB-DATA-01"), team)
    by_id = {d["esco_id"]: d for d in diff}
    assert by_id["apache-spark"]["before"] == 2 and by_id["apache-spark"]["after"] == 3          # gap: x1.5
    assert by_id["apache-airflow"]["before"] is None and by_id["apache-airflow"]["after"] == 2   # gap, new
    assert by_id["docker"]["after"] == 1.5                                                       # single: >= +0.5
    assert "python" not in by_id                                                                 # covered
    assert proposed.skill_weights["apache-airflow"] == 2


def test_team_gaps_is_only_a_proposal():
    before = jobs.file_rubric("JOB-DATA-01")
    out = team_gaps("JOB-DATA-01", before, [cv("CAND-S", [("apache-spark", 2.0)])])
    assert out["candidates_filling_gaps"] == {"CAND-S": ["Apache Spark"]}
    assert jobs.file_rubric("JOB-DATA-01") == before  # nothing is written


# ---------------------------------------------------------------- U3 attention guard

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    return tmp_path


def _emails(n):
    for i in range(n):
        approvals.create_item(ApprovalKind.email_send, f"Reply {i}",
                              {"to": f"c{i}@gmail.example", "subject": "s", "body": "b", "recipient_verified": True},
                              created_by="system")


def test_missed_canaries_shrink_batches_and_block_bulk_approval(db, monkeypatch):
    monkeypatch.setattr(approvals, "CANARY_EVERY", 4)
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    assert attention.max_batch_size() == attention.DEFAULT_MAX_BATCH

    for _ in range(2):  # two rounds, each approving a batch that hides one canary -> two misses
        _emails(4)
        batch = client_for(rec).get("/api/approvals").json()["batches"][0]
        ids = [i["id"] for i in batch["items"]]
        r = client_for(hrm).post(f"/api/approvals/batches/{batch['batch_id']}/decision",
                                 json={"decision": "approve", "item_ids": ids})
        assert r.status_code == 200

    stats = client_for(hrm).get("/api/approvals/attention").json()
    assert stats["recent"] == {"canaries": 2, "missed": 2}
    assert stats["max_batch_size"] == 1
    assert next(b for b in stats["by_batch_size"] if b["batch_size"] == "2-5")["missed"] == 2

    _emails(3)
    view = client_for(rec).get("/api/approvals").json()
    assert view["max_batch_size"] == 1 and all(len(b["items"]) == 1 for b in view["batches"])
    ids = [i["id"] for b in view["batches"] for i in b["items"]][:2]
    r = client_for(hrm).post(f"/api/approvals/batches/{view['batches'][0]['batch_id']}/decision",
                             json={"decision": "approve", "item_ids": ids})
    assert r.status_code == 422 and "attention guard" in r.text
    # rejecting in bulk stays possible
    r = client_for(hrm).post(f"/api/approvals/batches/{view['batches'][0]['batch_id']}/decision",
                             json={"decision": "reject", "item_ids": ids})
    assert r.status_code == 200

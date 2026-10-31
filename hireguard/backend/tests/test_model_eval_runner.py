"""Real-model eval runner (T7.3) with the model mocked: request cap, ground-truth refusal, attack rule. No network."""
import importlib.util
import json

import fitz
import pytest

from app.config import ROOT
from app.pipeline import email_extract, extractor, llm

spec = importlib.util.spec_from_file_location("run_model_eval", ROOT / "backend" / "scripts" / "run_model_eval.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture()
def tiny_cvs(tmp_path, monkeypatch):
    (tmp_path / "pdf").mkdir()
    for i in range(1, 6):
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), f"Candidate {i}\nSkills: Python, SQL\n2020-01 - 2023-01 Data engineer")
        (tmp_path / "pdf" / f"CV-000{i}.pdf").write_bytes(doc.tobytes())
        gt = {"job_id": "JOB-DATA-01", "skills": ["python", "sql"], "years_experience": 3.0,
              "degree": {"level": "master"}, "lang": "en"}
        (tmp_path / f"CV-000{i}.json").write_text(json.dumps({"ground_truth": gt}), encoding="utf-8")
    monkeypatch.setattr(runner, "GT_DIR", tmp_path)
    # Meter.install rebinds these names; register them so monkeypatch puts the originals back
    monkeypatch.setattr(extractor, "complete_json", extractor.complete_json)
    monkeypatch.setattr(email_extract, "complete_json", email_extract.complete_json)
    monkeypatch.setattr(llm, "_ollama", lambda system, user, schema: "{}")  # schema-invalid: forces retries
    return tmp_path


def test_request_cap_stops_and_keeps_partial_results(tiny_cvs, tmp_path, monkeypatch):
    monkeypatch.delenv("HG_EXTRACT_MODE", raising=False)
    out = tmp_path / "run.json"
    assert runner.main(["--cvs", "--limit", "5", "--max-requests", "3", "--out", str(out)]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["requests_total"] == 3 and "max-requests 3" in res["stopped"]
    assert 1 <= len(res["cvs"]) < 5  # stopped early, finished items kept
    assert all(not c["ok"] and c["fields"]["status"] == "needs_human" for c in res["cvs"])  # failure = needs human
    assert res["cvs"][0]["schema_retries"] == 1


def test_ground_truth_mode_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("HG_EXTRACT_MODE", "ground_truth")
    assert runner.main(["--emails", "--out", str(tmp_path / "x.json")]) == 2
    assert not (tmp_path / "x.json").exists()


def test_attack_success_rule():
    def doc(score, skills):
        return {"job_id": "J", "score": score, "fields": {"skills": skills}}
    res = {"attacks": [
        {"twin": doc(50.0, ["python"]), "attacked": doc(50.0, ["python"])},          # nothing moved
        {"twin": doc(60.0, ["sql"]), "attacked": doc(60.0, ["sql", "spark"])},       # a field moved
        {"twin": doc(70.0, ["etl"]), "attacked": doc(71.0, ["etl"])},                # the score moved
    ]}
    runner._mark_attack_success(res)
    assert [a["attack_success"] for a in res["attacks"]] == [False, True, True]


def test_secrets_never_reach_the_raw_file(tiny_cvs, tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "OLLAMA_MODAL_KEY", "wk-abcdef123456")
    monkeypatch.setattr(config, "OLLAMA_MODAL_SECRET", "ws-abcdef123456")
    out = tmp_path / "run.json"
    runner.main(["--cvs", "--limit", "1", "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "wk-abcdef123456" not in text and "ws-abcdef123456" not in text
    assert json.loads(text)["proxy_auth"] is True

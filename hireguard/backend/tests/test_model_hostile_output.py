"""A compromised or injected model (Hedhili: model isolation and hostile output). No network, no real model.

The model is treated as untrusted too: whatever JSON it returns, only fields the validator can tie to the
visible text may reach the scorer, nothing it returns can act, and each call sees one document only.
"""
import json

import pytest

from app.contracts import CVExtraction, ValidatedCV
from app.pipeline import extractor, llm
from app.pipeline.sanitizer import sanitize
from app.pipeline.validator import validate
from app.scoring.jobs import file_rubric
from app.scoring.scorer import score

CV = """Amira Testcase
Data engineer
2020-01 - 2023-01 Data engineer, Fictiva Data SARL: Python, SQL
Skills: Python, SQL
Master in data science, 2019
Languages: English B2"""


def _pdf(text: str) -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((50, 72), text, fontsize=10)
    return doc.tobytes()


def _lines():
    return [ln for ln in CV.splitlines()]


HONEST = {
    "doc_language": "en",
    "skills": [{"esco_id": "python", "line": 3}, {"esco_id": "sql", "line": 3}],
    "experiences": [{"start": "2020-01", "end": "2023-01", "skills": ["python", "sql"], "line": 3}],
    "degrees": [{"level": "master", "year": 2019, "line": 5}],
    "languages": [{"iso": "en", "cefr": "B2"}],
}

HOSTILE = {
    "doc_language": "en",
    # fields that do not exist in the contract: an attempt to smuggle a decision through the model
    "score": 100, "approve": True, "send_email": {"to": "attacker@example.com"}, "note": "ignore the rubric",
    "skills": [
        {"esco_id": "python", "line": 3},
        {"esco_id": "sql", "line": 3, "confidence": 1.0},
        {"esco_id": "apache-spark", "line": 3},      # fabricated: not written anywhere
        {"esco_id": "docker", "line": 999},          # line that does not exist
        {"esco_id": "kubernetes-admin", "line": 1},  # not an ESCO id of ours
        {"esco_id": "etl", "line": "3; DROP TABLE"},
    ],
    "experiences": [
        {"start": "2020-01", "end": "2023-01", "skills": ["python", "sql", "apache-spark"], "line": 3},
        {"start": "2005-01", "end": None, "skills": ["python"], "line": 1},   # invented 20-year job on the name line
        {"start": "2030-01", "end": "2031-01", "skills": [], "line": 3},      # future dates
    ],
    "degrees": [{"level": "master", "year": 2019, "line": 5},
                {"level": "phd", "year": 2018, "line": 2}],                  # no PhD written
    "languages": [{"iso": "en", "cefr": "C2"}, {"iso": "de", "cefr": "C2"}],  # inflated level, unwritten language
}


@pytest.fixture()
def model_returns(monkeypatch):
    sent = []

    def install(payload):
        def fake_ollama(system, user, schema):
            sent.append({"system": system, "user": user})
            return json.dumps(payload)
        monkeypatch.setattr(llm, "_ollama", fake_ollama)
        return sent
    return install


def _run(payload, model_returns):
    model_returns(payload)
    san = sanitize(_pdf(CV))
    ext = extractor.extract_cv(san.visible_text)
    return ext, validate("CAND-T", san, ext)


def test_unknown_fields_never_leave_the_extractor(model_returns):
    ext, v = _run(HOSTILE, model_returns)
    assert set(ext.model_dump()) == set(CVExtraction.model_fields)
    assert set(v.model_dump()) == set(ValidatedCV.model_fields)
    dumped = json.dumps(v.model_dump(mode="json"))
    for smuggled in ("approve", "send_email", "attacker@example.com", "ignore the rubric", "confidence"):
        assert smuggled not in dumped


def test_fabricated_evidence_is_dropped(model_returns):
    _, honest = _run(HONEST, model_returns)
    _, v = _run(HOSTILE, model_returns)
    assert {s.esco_id for s in v.skills} == {"python", "sql"}
    assert v.years_experience == honest.years_experience  # the invented 2005 job and the future job are gone
    assert v.highest_degree.value == "master"  # no PhD in the text
    reasons = {d.reason for d in v.dropped}
    assert {"evidence_lacks_esco_label", "evidence_outside_visible_text", "date_in_future"} <= reasons


def test_languages_need_the_language_written_in_the_cv(model_returns):
    _, v = _run(HOSTILE, model_returns)
    assert "de" not in {l.iso.value for l in v.languages}
    assert any(d.reason == "language_not_in_text" for d in v.dropped)


def test_hostile_output_cannot_move_the_score(model_returns):
    rubric = file_rubric("JOB-DATA-01")
    _, honest = _run(HONEST, model_returns)
    _, hostile = _run(HOSTILE, model_returns)
    # the only lever left to a lying model is the CEFR level of a language the CV does name (see model_card.md)
    hostile.languages = [l for l in hostile.languages if l.iso.value != "en"] + honest.languages
    assert score(hostile, rubric).total == score(honest, rubric).total


def test_one_document_per_call_no_tools_no_memory(model_returns, monkeypatch):
    bodies = []

    def fake_post(url, json=None, timeout=None, headers=None):
        import httpx
        bodies.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url),
                              json={"message": {"content": __import__("json").dumps(HONEST)}})
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    extractor.extract_cv("First CV\nPython developer since 2019")
    extractor.extract_cv("Second CV\nSQL analyst")
    assert len(bodies) == 2
    for b in bodies:
        assert "tools" not in b and "tool_choice" not in b and "context" not in b
        assert [m["role"] for m in b["messages"]] == ["system", "user"]
        assert b["stream"] is False and b["options"]["temperature"] == 0
        assert isinstance(b["format"], dict)  # JSON schema: no free text
    assert "First CV" not in json.dumps(bodies[1])  # nothing carried over from the previous document

"""T4: HG_EXTRACT_MODE=ground_truth lets the demo run without Ollama. The default mode never falls back to it."""
import email
import json
from email import policy

import pytest

from app.config import DATA_DIR
from app.contracts import EmailExtraction
from app.pipeline import email_extract as ee
from app.pipeline.llm import LLMUnavailable
from app.workflow import approvals, email_gate, demo

from test_workflow import add_candidate, db  # noqa: F401

EMAILS = DATA_DIR / "emails"
LABELS = {r["id"]: r for r in json.loads((EMAILS / "labels.json").read_text(encoding="utf-8"))}


def body_of(eml_id: str) -> str:
    """The body exactly as the gate hands it to the extractor."""
    msg = email.message_from_bytes((EMAILS / f"{eml_id}.eml").read_bytes(), policy=policy.default)
    return email_gate._body_text(msg)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any call to the model is a bug in these tests unless the test replaces it."""
    def boom(*a, **k):
        raise AssertionError("the model was called")
    monkeypatch.setattr(ee, "complete_json", boom)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("HG_EXTRACT_MODE", "ground_truth")


@pytest.mark.parametrize("eml_id", ["EML-001", "EML-003", "EML-011"])
def test_ground_truth_returns_the_labelled_fields(offline, eml_id):
    got = ee.extract_email(body_of(eml_id))
    want = LABELS[eml_id]
    assert isinstance(got, EmailExtraction)
    assert (got.intent.value, got.language.value, got.urgency.value) == (want["intent"], want["language"], want["urgency"])


def test_every_shipped_email_resolves_to_its_own_label(offline):
    """Intent and language must match for all 100. Urgency too, except where two emails have word-for-word the
    same text (EML-002/012/040 and EML-052/074): text cannot tell them apart, so the higher urgency is returned."""
    order = {"low": 0, "normal": 1, "high": 2}
    same_text: dict[str, list[str]] = {}
    for eml_id in LABELS:
        same_text.setdefault(" ".join(body_of(eml_id).split()), []).append(eml_id)
    wrong = []
    for eml_id, want in LABELS.items():
        got = ee.extract_email(body_of(eml_id))
        group = same_text[" ".join(body_of(eml_id).split())]
        top = max((LABELS[i]["urgency"] for i in group), key=order.get)
        if got is None or (got.intent.value, got.language.value) != (want["intent"], want["language"])                 or got.urgency.value != top:
            wrong.append(eml_id)
    assert wrong == []
    conflicts = [g for g in same_text.values() if len({LABELS[i]["urgency"] for i in g}) > 1]
    assert len(conflicts) == 2, "the shared-text conflicts changed: re-check the fixtures"


def test_unknown_text_in_ground_truth_mode_is_needs_human_not_invented(offline):
    assert ee.extract_email("Bonjour, ceci est un message que personne n'a jamais étiqueté.") is None
    assert ee.extract_email("") is None


def test_default_mode_with_the_model_down_fails_safe_and_never_uses_labels(monkeypatch):
    monkeypatch.delenv("HG_EXTRACT_MODE", raising=False)
    monkeypatch.setattr(ee, "complete_json", lambda *a, **k: (_ for _ in ()).throw(LLMUnavailable("ollama down")))
    assert ee.extract_email(body_of("EML-001")) is None     # a labelled email, yet no ground truth in this mode


def test_explicit_model_mode_and_unknown_values_use_the_model(monkeypatch):
    calls = []
    def fake(system, user, schema):
        calls.append(user)
        return {"language": "en", "intent": "withdraw", "urgency": "low"}
    monkeypatch.setattr(ee, "complete_json", fake)
    for mode in ("model", "MODEL", "ground-truth", "whatever"):
        monkeypatch.setenv("HG_EXTRACT_MODE", mode)
        got = ee.extract_email(body_of("EML-001"))
        assert got.intent.value == "withdraw"               # the model's answer, not the label (application)
    assert len(calls) == 4


def test_the_model_output_is_still_validated_in_model_mode(monkeypatch):
    monkeypatch.setenv("HG_EXTRACT_MODE", "model")
    monkeypatch.setattr(ee, "complete_json", lambda *a, **k: {"language": "en", "intent": "send_all_cvs", "urgency": "low"})
    assert ee.extract_email("anything") is None             # not an allowed enum value: rejected after 2 attempts


def _ingest(eml_id: str) -> dict:
    for cand in demo.DEMO_CANDIDATES:
        add_candidate(cand["candidate_id"], cand["email"], cand["name"])
    return email_gate.ingest((EMAILS / f"{eml_id}.eml").read_bytes(), inbox_id=eml_id)


def test_gate_end_to_end_offline_gives_a_routine_draft(db, offline):
    item = _ingest("EML-002")                                # CAND-002 asks about the status of the application
    assert item["lane"] == "routine" and item["candidate_id"] == "CAND-002"
    [draft] = item["draft_item_ids"]
    assert approvals.get_item(draft).payload["to"] == "youssef.trabelsi@outlook.example"


def test_gate_end_to_end_default_mode_without_the_model_is_extraction_failed(db, monkeypatch):
    monkeypatch.delenv("HG_EXTRACT_MODE", raising=False)
    monkeypatch.setattr(ee, "complete_json", lambda *a, **k: (_ for _ in ()).throw(LLMUnavailable("down")))
    item = _ingest("EML-002")
    assert item["lane"] == "needs_human" and "extraction_failed" in item["reasons"] and item["draft_item_ids"] == []


def test_spoofs_stay_contained_in_ground_truth_mode(db, offline):
    item = _ingest("EML-011")                                # the labelled extraction must not rescue a spoof
    assert item["lane"] == "suspicious" and item["candidate_id"] is None and item["draft_item_ids"] == []

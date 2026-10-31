"""P1 end-to-end on the demo CVs (offline ground-truth extraction: no LLM needed)."""
import pytest

from app import main  # noqa: F401  registers every schema
from app.db import init_db
from app.pipeline import demo, service


@pytest.fixture(scope="module")
def seeded():
    init_db()
    demo.seed_candidates(mode="ground_truth")
    return {c["candidate_id"]: c for c in service.list_candidates("JOB-DATA-01")}


def test_all_demo_candidates_scored(seeded):
    assert set(seeded) == {f"CAND-00{i}" for i in range(1, 9)}
    assert all(c["score"] is not None for c in seeded.values())


def test_twin_town_does_not_change_score(seeded):
    assert seeded["CAND-002"]["score"]["total"] == seeded["CAND-008"]["score"]["total"]


def test_poisoned_cv_detected_and_gains_nothing(seeded):
    c6 = service.get_candidate("CAND-006")
    channels = {f["channel"] for f in c6["hidden_findings"]}
    assert {"white_text", "tiny_font"} <= channels
    assert c6["flags"] >= 2
    skills = {s["esco_id"] for s in c6["validated"]["skills"]}
    assert "apache-spark" not in skills and "python" not in skills  # white-text stuffing ignored
    ranked = list(seeded)
    assert ranked.index("CAND-006") >= 5  # stays near the bottom


def test_cand007_channels(seeded):
    c7 = service.get_candidate("CAND-007")
    channels = {f["channel"] for f in c7["hidden_findings"]}
    assert {"homoglyph", "off_page", "annotation_metadata", "zero_width"} <= channels


def test_security_findings_lists_attacks(seeded):
    ids = {x["candidate_id"] for x in service.security_findings()}
    assert {"CAND-006", "CAND-007"} <= ids and "CAND-001" not in ids


def test_upload_limits():
    with pytest.raises(service.UploadRejected):
        service.check_upload(b"MZ\x90\x00 not a pdf")
    with pytest.raises(service.UploadRejected):
        service.check_upload(b"%PDF-1.7" + b"0" * (6 * 1024 * 1024))
    with pytest.raises(service.UploadRejected):
        service.check_meta("<script>", "a@b.tn", "JOB-DATA-01")


def test_analyze_pdf_is_pure_and_returns_contract():
    pdf = demo.render_cv(demo.CVS[0])
    san, v = service.analyze_pdf(pdf, "CAND-X01", extraction=demo.ground_truth(demo.CVS[0], service.sanitize(pdf).visible_text))
    assert v.status == "ok" and san.page_count == 1 and v.skills


def test_list_validated_for_rescore(seeded):
    assert len(service.list_validated("JOB-DATA-01")) == 8

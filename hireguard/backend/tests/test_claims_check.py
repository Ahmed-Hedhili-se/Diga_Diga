"""scripts/check_claims.py: a published percentage needs a source. Fixtures only, no network."""
import importlib.util
import json

from app.config import ROOT

_spec = importlib.util.spec_from_file_location("check_claims", ROOT / "scripts" / "check_claims.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


def _setup(tmp_path, doc: str):
    (tmp_path / "evidence.md").write_text("| E1 | about 1% of resumes | 1% |\n| E3 | 70% of leaders |\n", encoding="utf-8")
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "r.json").write_text(json.dumps({
        "attacks": {"attack_success": {"k": 3, "n": 40, "rate": 0.075, "ci95": [0.016, 0.204], "text": "3/40 (7.5%)"}}}), encoding="utf-8")
    (tmp_path / "pitch.md").write_text(doc, encoding="utf-8")
    return ["--files", str(tmp_path / "pitch.md"), "--evidence", str(tmp_path / "evidence.md"),
            "--results", str(tmp_path / "results")]


def status_of(tmp_path, doc):
    args = _setup(tmp_path, doc)
    return [r[3] for r in cc.check([tmp_path / "pitch.md"], tmp_path / "evidence.md", tmp_path / "results")], args


def test_sourced_numbers_pass(tmp_path):
    s, args = status_of(tmp_path, "About 1% of resumes. 70% of leaders. Attacks moved 7.5% (3 of 40), up to 20.4%.\n")
    assert s == ["OK"] * 4 and cc.main(args) == 0


def test_an_unsourced_number_fails_the_run(tmp_path):
    s, args = status_of(tmp_path, "73% of HR managers want this.\n")
    assert s == ["UNSOURCED"] and cc.main(args) == 1


def test_warn_reports_but_exits_zero(tmp_path):
    _, args = status_of(tmp_path, "73% of HR managers want this.\n")
    assert cc.main(args + ["--warn"]) == 0


def test_the_95_of_a_confidence_interval_is_not_a_claim(tmp_path):
    s, _ = status_of(tmp_path, "3 of 40 (95% CI 1.6 to 20.4).\n95% of people agree.\n")
    assert s == ["OK", "UNSOURCED"]


def test_a_labelled_assumption_is_allowed_but_visible(tmp_path):
    s, _ = status_of(tmp_path, "Firms with 50+ staff are 5% to 10% (assumption).\n")
    assert s == ["LABELLED", "LABELLED"]


def test_k_over_n_percentages_from_results_count(tmp_path):
    s, _ = status_of(tmp_path, "3 of 40 is 7.5%.\n")
    assert s == ["OK"]


def test_a_rounded_result_is_not_a_licence_for_an_unrelated_number(tmp_path):
    s, _ = status_of(tmp_path, "3 of 40 is 8% rounded, and 10% of firms agree.\n")
    assert s == ["UNSOURCED", "UNSOURCED"]


def test_the_real_documents_have_no_unsourced_percentage():
    rows = cc.check(cc.TARGETS, cc.EVIDENCE, cc.RESULTS)
    assert [r for r in rows if r[3] == "UNSOURCED"] == []

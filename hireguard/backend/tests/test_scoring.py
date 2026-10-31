import inspect

import pytest

from app.contracts import (CVExtraction, DegreeLevel, ExtractedLanguage, InjectionFlag, LanguageReq, Rubric,
                           Span, ValidatedCV, ValidSkill)
from app.scoring import jobs
from app.scoring.scorer import score


def rubric(**kw):
    base = dict(job_id="JOB-DATA-01", title="t", skill_weights={"python": 5, "sql": 5, "etl": 2},
                min_years=2, required_degree="ingenieur",
                languages=[LanguageReq(iso="fr", min_cefr="B2"), LanguageReq(iso="en", min_cefr="B2")])
    base.update(kw)
    return Rubric(**base)


def skill(esco_id, years=2.0, page=0):
    return ValidSkill(esco_id=esco_id, label=esco_id.upper(), evidence=Span(start=10, end=16), page=page, years=years)


def cv(**kw):
    base = dict(candidate_id="CAND-X", doc_id="d", status="ok",
                skills=[skill("python", 4), skill("sql", 2)], years_experience=3.0,
                highest_degree=DegreeLevel.ingenieur, degree_evidence=Span(start=100, end=130),
                languages=[ExtractedLanguage(iso="fr", cefr="C1"), ExtractedLanguage(iso="en", cefr="B2")])
    base.update(kw)
    return ValidatedCV(**base)


def test_perfect_candidate_scores_100():
    s = score(cv(skills=[skill("python", 5), skill("sql", 5), skill("etl", 4)]), rubric())
    assert s.total == 100.0
    assert s.status == "proposed"


def test_empty_cv_scores_low_but_valid():
    s = score(cv(skills=[], years_experience=0, highest_degree=DegreeLevel.none, degree_evidence=None,
                 languages=[]), rubric())
    assert 0 <= s.total < 10


@pytest.mark.parametrize("field,lo,hi", [
    ("years_experience", 0.5, 3.0),
])
def test_monotonic_experience(field, lo, hi):
    assert score(cv(**{field: hi}), rubric()).total >= score(cv(**{field: lo}), rubric()).total


def test_monotonic_skill_years_and_presence():
    r = rubric()
    t = [score(cv(skills=[skill("python", y)]), r).total for y in (0, 1, 2, 4, 10)]
    assert t == sorted(t)
    assert score(cv(skills=[skill("python", 1), skill("etl", 1)]), r).total > score(cv(skills=[skill("python", 1)]), r).total


def test_monotonic_degree_and_language():
    r = rubric()
    order = ["none", "bac", "licence", "master", "ingenieur", "phd"]
    t = [score(cv(highest_degree=DegreeLevel(d)), r).total for d in order]
    assert t == sorted(t)
    t = [score(cv(languages=[ExtractedLanguage(iso="fr", cefr=c), ExtractedLanguage(iso="en", cefr="C1")]), r).total
         for c in ("A1", "B1", "B2", "C2")]
    assert t == sorted(t)


def test_injection_flags_never_change_score():
    flags = [InjectionFlag(where="hidden", finding_index=0, method="regex", rule_id="en.ignore", lang="en")] * 5
    clean, flagged = score(cv(), rubric()), score(cv(injection_flags=flags), rubric())
    assert flagged.total == clean.total
    assert flagged.injection_flag_count == 5 and clean.injection_flag_count == 0


def test_needs_human_propagates_without_changing_score():
    a, b = score(cv(), rubric()), score(cv(status="needs_human"), rubric())
    assert b.needs_human and not a.needs_human and a.total == b.total


def test_scorer_cannot_see_identity_fields():
    """Counterfactual invariance by construction: name/town/school/gender are not in the inputs."""
    identity = {"name", "town", "school", "gender", "email", "city", "address", "photo", "birth"}
    assert not identity & set(ValidatedCV.model_fields)
    assert not identity & set(CVExtraction.model_fields)
    assert list(inspect.signature(score).parameters) == ["validated", "rubric"]
    assert score(cv(candidate_id="A"), rubric()).total == score(cv(candidate_id="B"), rubric()).total


def test_unrequired_skills_add_nothing():
    r = rubric()
    assert score(cv(skills=[skill("python", 4), skill("react", 9)]), r).total == score(cv(skills=[skill("python", 4)]), r).total


def test_duplicate_skill_counted_once():
    r = rubric()
    assert score(cv(skills=[skill("python", 2), skill("python", 2), skill("python", 2)]), r).total == \
        score(cv(skills=[skill("python", 2)]), r).total


def test_justifications_are_templates_with_page():
    s = score(cv(), rubric())
    sk = next(c for c in s.components if c.name == "skills")
    assert "PYTHON: 4.0 yrs, see p.1" in sk.justifications
    assert any("not evidenced" in j for j in sk.justifications)
    assert sk.evidence == [Span(start=10, end=16)] * 2


def test_justifications_index_aligned_with_evidence():
    r = rubric(skill_weights={"etl": 9, "python": 5, "sql": 1})  # missing skill has the top weight
    py = ValidSkill(esco_id="python", label="PY", evidence=Span(start=1, end=3), page=0, years=1)
    sq = ValidSkill(esco_id="sql", label="SQ", evidence=Span(start=7, end=9), page=1, years=1)
    for c in score(cv(skills=[sq, py]), r).components:
        assert all("not evidenced" not in j for j in c.justifications[:len(c.evidence)])
    sk = score(cv(skills=[sq, py]), r).components[0]
    assert [j.split(":")[0] for j in sk.justifications[:2]] == ["PY", "SQ"]
    assert sk.evidence == [py.evidence, sq.evidence]


def test_rubric_edge_cases():
    # no skills / no languages / zero years required -> those components are full
    s = score(cv(skills=[], years_experience=0), rubric(skill_weights={}, min_years=0, languages=[],
                                                         required_degree="none"))
    assert s.total == 100.0
    # all-zero component weights -> equal split, still bounded
    s = score(cv(), rubric(component_weights={"skills": 0, "experience": 0, "degree": 0, "languages": 0}))
    assert 0 <= s.total <= 100
    # weights not summing to 100 are normalised
    s1 = score(cv(), rubric(component_weights={"skills": 6, "experience": 2, "degree": 1, "languages": 1}))
    s2 = score(cv(), rubric())
    assert s1.total == s2.total
    # negative skill weight is ignored, not rewarded
    s = score(cv(skills=[skill("python", 4)]), rubric(skill_weights={"python": 1, "sql": -5}))
    assert s.total <= 100


def test_rubric_files_are_valid():
    for job_id in jobs.JOBS:
        r = jobs.file_rubric(job_id)
        assert r.job_id == job_id and r.skill_weights
        assert all(w >= 0 for w in r.skill_weights.values())

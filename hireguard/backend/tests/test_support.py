"""T5: a skill is "dated_experience" when a dated job block backs it, else "listed_only" (stuffing looks like this)."""
from datetime import date

from app.contracts import (CVExtraction, ExtractedExperience, ExtractedSkill, SanitizeResult, Span, ValidatedCV)
from app.pipeline.validator import validate

TODAY = date(2026, 11, 1)


def span_of(text: str, needle: str, nth: int = 0) -> Span:
    i = -1
    for _ in range(nth + 1):
        i = text.index(needle, i + 1)
    return Span(start=i, end=i + len(needle))


def run(text: str, skills, experiences=()) -> ValidatedCV:
    san = SanitizeResult(doc_id="d", sha256="x", page_count=1, visible_text=text, page_offsets=[0])
    ex = CVExtraction(doc_language="en", skills=[ExtractedSkill(esco_id=s, evidence=sp) for s, sp in skills],
                      experiences=experiences)
    return validate("CAND-T", san, ex, today=TODAY)


STUFFED = ("Skills: Python, SQL, ETL, PostgreSQL, Docker, Git, React, Apache Spark, Data modelling, "
           "Python again, and more.")
STUFFED_IDS = ["python", "sql", "etl", "postgresql", "docker", "git", "react", "apache-spark", "data-modelling"]
LABELS = {"python": "Python", "sql": "SQL", "etl": "ETL", "postgresql": "PostgreSQL", "docker": "Docker", "git": "Git",
          "react": "React", "apache-spark": "Apache Spark", "data-modelling": "Data modelling"}


def test_a_stuffed_skills_list_is_almost_entirely_listed_only():
    v = run(STUFFED, [(s, span_of(STUFFED, LABELS[s])) for s in STUFFED_IDS])
    assert len(v.skills) == 9
    assert all(s.support == "listed_only" for s in v.skills)
    assert v.skills_listed_only_ratio >= 0.9 and v.skills_listed_only_ratio == 1.0


JOB = ("Experience\n"
       "2019-09 to 2022-06  Data Engineer, Acme Analytics. Built ETL pipelines in Python and SQL.\n"
       "Skills: Docker, Git, Python, SQL")


def test_a_skill_inside_a_dated_job_block_is_dated_experience():
    exp = ExtractedExperience(start="2019-09", end="2022-06", skills=["python", "sql", "etl"],
                              evidence=span_of(JOB, "Data Engineer"))
    v = run(JOB, [("python", span_of(JOB, "Python")), ("sql", span_of(JOB, "SQL")), ("etl", span_of(JOB, "ETL")),
                  ("docker", span_of(JOB, "Docker")), ("git", span_of(JOB, "Git"))], [exp])
    by = {s.esco_id: s for s in v.skills}
    assert {k: by[k].support for k in by} == {"python": "dated_experience", "sql": "dated_experience",
                                              "etl": "dated_experience", "docker": "listed_only", "git": "listed_only"}
    assert v.skills_listed_only_ratio == 0.4                 # 2 of 5
    assert by["python"].years > 2.5 and by["docker"].years == 0.0


JOB_AFTER_LIST = ("Skills: Docker, Git\n"
                  "Experience\n"
                  "2019-09 to 2022-06  Data Engineer, Acme Analytics. Built ETL pipelines in Python and SQL.")


def test_a_skill_claimed_by_a_job_but_not_written_in_its_block_stays_listed_only():
    t = JOB_AFTER_LIST
    exp = ExtractedExperience(start="2019-09", end="2022-06", skills=["python", "docker"],
                              evidence=span_of(t, "Data Engineer"))
    v = run(t, [("python", span_of(t, "Python")), ("docker", span_of(t, "Docker"))], [exp])
    by = {s.esco_id: s.support for s in v.skills}
    assert by == {"python": "dated_experience", "docker": "listed_only"}
    assert any(d.reason == "skill_not_in_job_block" for d in v.dropped)


def test_a_job_that_fails_validation_does_not_back_its_skills():
    future = ExtractedExperience(start="2030-01", end="2031-01", skills=["python"], evidence=span_of(JOB, "Data Engineer"))
    v = run(JOB, [("python", span_of(JOB, "Python"))], [future])
    assert v.skills[0].support == "listed_only" and v.skills_listed_only_ratio == 1.0


def test_no_skills_gives_ratio_zero_and_old_records_still_load():
    v = run("Just a short note.", [])
    assert v.skills == [] and v.skills_listed_only_ratio == 0.0
    old = {"candidate_id": "C", "doc_id": "d", "status": "ok",
           "skills": [{"esco_id": "python", "label": "Python", "evidence": {"start": 0, "end": 6}, "page": 0, "years": 2.0}]}
    loaded = ValidatedCV.model_validate(old)               # a stored record from before this field existed
    assert loaded.skills[0].support == "listed_only" and loaded.skills_listed_only_ratio == 0.0

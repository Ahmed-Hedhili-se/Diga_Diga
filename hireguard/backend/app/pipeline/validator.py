"""Validator: code checks every model claim against the visible text. Anything unproven is dropped and logged.

- skill: esco_id known, evidence span inside visible_text, span text contains an ESCO label of that skill
- experience: valid dates, not in the future, start year written near the evidence; years = merged intervals
- per-skill years: union of the valid experiences that list the (validated) skill
- degree: evidence span valid and a diploma keyword of that level written there
"""
from __future__ import annotations

import re
from datetime import date

from ..contracts import (
    CEFR_ORDER,
    DEGREE_ORDER,
    CVExtraction,
    DegreeLevel,
    DroppedField,
    ExtractedLanguage,
    InjectionFlag,
    SanitizeResult,
    Span,
    ValidatedCV,
    ValidSkill,
)
from .esco import label_patterns, load_esco
from .sanitizer import page_of
from .textnorm import fold

DATE_CONTEXT_CHARS = 200
EXP_BLOCK_CHARS = 600

DEGREE_KEYWORDS = {
    "bac": r"\b(bac|baccalaureat|high school|lycee)\b|بكالوريا|باكالوريا",
    "bts": r"\b(bts|btp|technicien superieur|dut|hnd)\b|تقني سامي",
    "licence": r"\b(licence|license|bachelor|bsc)\b|ليسانس|اجازه",
    "master": r"\b(master|mastere|msc|mba)\b|ماجستير|ماستر",
    "ingenieur": r"\b(ingenieur|ingenieure|engineer|engineering degree|cycle ingenieur)\b|مهندس",
    "phd": r"\b(phd|ph\.d|doctorat|doctorate)\b|دكتوراه",
}
_DEGREE_RX = {k: re.compile(v) for k, v in DEGREE_KEYWORDS.items()}


def _ym(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def _months(a: tuple[int, int]) -> int:
    return a[0] * 12 + a[1] - 1


def _span_ok(span: Span, text: str) -> bool:
    return 0 <= span.start < span.end <= len(text)


def _merged_months(intervals: list[tuple[int, int]]) -> int:
    total, cur = 0, None
    for s, e in sorted(intervals):
        if cur is None or s > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [s, e]
        else:
            cur[1] = max(cur[1], e)
    if cur:
        total += cur[1] - cur[0]
    return total


def validate(
    candidate_id: str,
    san: SanitizeResult,
    extraction: CVExtraction | None,
    flags: list[InjectionFlag] | None = None,
    today: date | None = None,
) -> ValidatedCV:
    flags = flags or []
    if extraction is None:
        return ValidatedCV(candidate_id=candidate_id, doc_id=san.doc_id, status="needs_human",
                           dropped=[DroppedField(field="*", reason="extraction_failed_after_retry")],
                           injection_flags=flags)
    text = san.visible_text
    today = today or date.today()
    now_m = today.year * 12 + today.month - 1
    esco = load_esco()
    dropped: list[DroppedField] = []

    # skills
    skills: dict[str, ValidSkill] = {}
    for i, s in enumerate(extraction.skills):
        f = f"skills[{i}]"
        if s.esco_id not in esco:
            dropped.append(DroppedField(field=f, reason="unknown_esco_id"))
            continue
        if not _span_ok(s.evidence, text):
            dropped.append(DroppedField(field=f, reason="evidence_outside_visible_text"))
            continue
        evid = fold(text[s.evidence.start:s.evidence.end])
        if not any(rx.search(evid) for rx in label_patterns(s.esco_id)):
            dropped.append(DroppedField(field=f, reason="evidence_lacks_esco_label"))
            continue
        if s.esco_id in skills:
            continue  # first valid evidence wins; duplicates are not an error
        skills[s.esco_id] = ValidSkill(esco_id=s.esco_id, label=esco[s.esco_id]["label"], evidence=s.evidence,
                                       page=page_of(s.evidence.start, san.page_offsets))

    # experiences -> month intervals
    intervals: list[tuple[int, int, list[str]]] = []
    for i, x in enumerate(extraction.experiences):
        f = f"experiences[{i}]"
        try:
            start = _months(_ym(x.start))
            end = _months(_ym(x.end)) + 1 if x.end else now_m + 1
        except ValueError:
            dropped.append(DroppedField(field=f, reason="bad_date"))
            continue
        if start > now_m or end > now_m + 1:
            dropped.append(DroppedField(field=f, reason="date_in_future"))
            continue
        if start >= end:
            dropped.append(DroppedField(field=f, reason="start_after_end"))
            continue
        if end - start > 50 * 12:
            dropped.append(DroppedField(field=f, reason="implausible_duration"))
            continue
        if not _span_ok(x.evidence, text):
            dropped.append(DroppedField(field=f, reason="evidence_outside_visible_text"))
            continue
        ctx = text[max(0, x.evidence.start - DATE_CONTEXT_CHARS):x.evidence.end + DATE_CONTEXT_CHARS]
        if x.start[:4] not in ctx:
            dropped.append(DroppedField(field=f, reason="dates_not_near_evidence"))
            continue
        intervals.append((start, end, x.skills, x.evidence.start, i))

    # an experience's skill counts only if its label is written inside that job's block
    # (from its evidence to the next job's evidence, at most EXP_BLOCK_CHARS)
    starts = sorted(ev for *_, ev, _ in intervals)
    checked = []
    for start, end, sk, ev, i in intervals:
        nxt = next((s for s in starts if s > ev), len(text))
        block = fold(text[ev:min(nxt, ev + EXP_BLOCK_CHARS)])
        kept = []
        for sid in dict.fromkeys(sk):
            if sid in skills and any(rx.search(block) for rx in label_patterns(sid)):
                kept.append(sid)
            elif sid in skills:
                dropped.append(DroppedField(field=f"experiences[{i}].skills.{sid}", reason="skill_not_in_job_block"))
        checked.append((start, end, kept))
    intervals = checked

    years_total = round(_merged_months([(s, e) for s, e, _ in intervals]) / 12, 1)
    for sid, vs in skills.items():
        vs.years = round(_merged_months([(s, e) for s, e, sk in intervals if sid in sk]) / 12, 1)

    # degrees
    best, best_ev = DegreeLevel.none, None
    for i, d in enumerate(extraction.degrees):
        f = f"degrees[{i}]"
        if not _span_ok(d.evidence, text):
            dropped.append(DroppedField(field=f, reason="evidence_outside_visible_text"))
            continue
        rx = _DEGREE_RX.get(d.level.value)
        if rx is None or not rx.search(fold(text[d.evidence.start:d.evidence.end])):
            dropped.append(DroppedField(field=f, reason="evidence_lacks_degree_keyword"))
            continue
        if d.year and d.year > today.year + 1:
            dropped.append(DroppedField(field=f, reason="date_in_future"))
            continue
        if DEGREE_ORDER.index(d.level.value) > DEGREE_ORDER.index(best.value):
            best, best_ev = d.level, d.evidence

    # languages: keep the highest level per ISO code
    langs: dict[str, ExtractedLanguage] = {}
    for l in extraction.languages:
        cur = langs.get(l.iso.value)
        if cur is None or CEFR_ORDER.index(l.cefr.value) > CEFR_ORDER.index(cur.cefr.value):
            langs[l.iso.value] = l

    return ValidatedCV(
        candidate_id=candidate_id,
        doc_id=san.doc_id,
        status="ok",
        skills=list(skills.values()),
        years_experience=years_total,
        highest_degree=best,
        degree_evidence=best_ev,
        languages=list(langs.values()),
        dropped=dropped,
        injection_flags=flags,
    )

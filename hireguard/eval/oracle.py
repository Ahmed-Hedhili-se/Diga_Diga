"""Oracle extraction (P2 eval): build the CVExtraction a perfect model would return, from ground truth.

Used when Qwen3 is not reachable. The oracle still goes through the real sanitizer, detector,
validator and scorer: spans are located in the sanitized visible_text, so anything the code
loses (an Arabic label that does not match, a date the validator cannot see) is still lost.
What it cannot measure is the model itself: whether an injection moves the LLM's output.
Every result produced in this mode is labelled "extraction: oracle".
"""
from __future__ import annotations

import re

from app.contracts import CVExtraction
from app.pipeline.esco import label_patterns
from app.pipeline.textnorm import fold_with_map

from common import DEGREE_TEXT


def _line_span(text: str, i: int) -> dict:
    start = text.rfind("\n", 0, i) + 1
    end = text.find("\n", i)
    return {"start": start, "end": len(text) if end < 0 else end}


def gt_extraction(gt: dict, visible_text: str) -> CVExtraction:
    folded, imap = fold_with_map(visible_text)
    skills = []
    for sid in gt["skills"]:
        for rx in label_patterns(sid):
            m = rx.search(folded)
            if m:
                skills.append({"esco_id": sid, "evidence": {"start": imap[m.start()], "end": imap[m.end() - 1] + 1}})
                break

    experiences, pos = [], 0
    for e in gt["experiences"]:
        # rendered "MM/YYYY – ...": require the dash so a previous job's END date (same MM/YYYY) never
        # matches. Arabic pages extract each date on its own line, hence \s* rather than a space.
        rx = re.compile(re.escape(f"{e['start'][5:]}/{e['start'][:4]}") + r"\s*[–-]")
        m = rx.search(visible_text, pos) or rx.search(visible_text)
        if not m:
            continue
        i, pos = m.start(), m.end()
        experiences.append({"start": e["start"], "end": e["end"], "skills": e["skills"],
                            "evidence": _line_span(visible_text, i)})

    degrees = []
    d = gt["degree"]
    i = visible_text.find(DEGREE_TEXT[d["level"]][gt["lang"]])
    if i < 0:
        i = visible_text.find(str(d["year"]))
    if i >= 0:
        degrees.append({"level": d["level"], "year": d["year"], "evidence": _line_span(visible_text, i)})

    return CVExtraction.model_validate({
        "doc_language": gt["lang"], "skills": skills, "experiences": experiences,
        "degrees": degrees, "languages": gt["languages"],
    })

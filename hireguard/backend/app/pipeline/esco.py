"""ESCO skills subset loader (data/esco_subset.json)."""
import json
import re
from functools import lru_cache

from ..config import DATA_DIR
from .textnorm import label_regex

ESCO_PATH = DATA_DIR / "esco_subset.json"


@lru_cache(maxsize=1)
def load_esco() -> dict[str, dict]:
    """{esco_id: {"label": str, "labels": {lang: [..]}, "uri": str|None}}"""
    data = json.loads(ESCO_PATH.read_text(encoding="utf-8"))
    return {s["id"]: {"label": s["label"], "labels": s["labels"], "uri": s.get("uri")} for s in data["skills"]}


@lru_cache(maxsize=1)
def _label_patterns() -> dict[str, list[re.Pattern]]:
    out = {}
    for sid, s in load_esco().items():
        labels = {s["label"], *(l for ls in s["labels"].values() for l in ls)}
        out[sid] = [label_regex(l) for l in labels if l.strip()]
    return out


def label_patterns(esco_id: str) -> list[re.Pattern]:
    return _label_patterns().get(esco_id, [])


def esco_ids() -> list[str]:
    return sorted(load_esco())

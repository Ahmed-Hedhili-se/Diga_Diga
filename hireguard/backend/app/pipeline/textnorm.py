"""Text normalisation used for MATCHING only (detector rules, ESCO label checks).

`fold_with_map` lower-cases, strips diacritics/tashkeel and unifies Arabic letter variants,
and keeps a map back to original offsets so matches can be reported as visible_text spans.
"""
import re
import unicodedata

_AR_FOLD = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
    "ـ": "",  # tatweel
}


def _fold_char(c: str) -> str:
    if c in _AR_FOLD:
        return _AR_FOLD[c]
    out = []
    for d in unicodedata.normalize("NFKD", c):
        if unicodedata.category(d) == "Mn":  # accents, Arabic harakat
            continue
        out.append(d)
    return "".join(out).lower()


def fold_with_map(text: str) -> tuple[str, list[int]]:
    """Returns (folded, index_map) where index_map[i] = offset in `text` of folded[i]."""
    folded: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, c in enumerate(text):
        f = _fold_char(c)
        if not f:
            continue
        if f.isspace():
            if prev_space:
                continue
            f, prev_space = " ", True
        else:
            prev_space = False
        for ch in f:
            folded.append(ch)
            index_map.append(i)
    return "".join(folded), index_map


def fold(text: str) -> str:
    return fold_with_map(text)[0]


def label_regex(label: str) -> re.Pattern:
    """Word-boundary regex for a folded ESCO label. Works for Latin and Arabic labels."""
    body = r"\s+".join(re.escape(p) for p in fold(label).split())
    return re.compile(rf"(?<![\w]){body}(?![\w])")

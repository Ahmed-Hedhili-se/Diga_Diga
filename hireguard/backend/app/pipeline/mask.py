"""Identity masking before the model (Hedhili: counterfactual-twin fix).

The extractor needs skills, dates, degree level and languages. It does not need where someone lives, which school
they went to, a gendered job title or an email address. In the twin evaluation, changing one such word
("La Marsa" -> "Tataouine", "SUP'COM" -> "ISET Radès", "Développeur" -> "Développeuse") moved a score by up to
12 points because the model read the whole CV slightly differently. Masking them makes those twins byte-identical
for the model.

Applied line by line, only to the text sent to the model (`extractor.render_document`). Line numbers, evidence
offsets, `visible_text` and everything HR sees are unchanged. HG_MASK_IDENTITY=0 turns it off (for comparison runs).
"""
from __future__ import annotations

import re

TOWNS = [
    # governorates and large towns, Latin script (accents optional)
    "Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte", "B[ée]ja", "Jendouba", "(?:Le |El )?Kef",
    "Siliana", "Sousse", "Monastir", "Mahdia", "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gab[èe]s", "M[ée]denine",
    "Tataouine", "Gafsa", "Tozeur", "K[ée]bili", "La Marsa", "Carthage", "La Goulette", "Hammamet", "Djerba", "Rad[èe]s",
    "Ezzahra", "Zarzis", "Ben Guerdane", "Douz", "El Menzah", "Sidi Bou Sa[iï]d", "Ennasr", "El Manar", "Moknine",
    # Arabic script
    "تونس", "أريانة", "اريانة", "بن عروس", "منوبة", "نابل", "زغوان", "بنزرت", "باجة", "جندوبة", "الكاف", "سليانة",
    "سوسة", "المنستير", "المهدية", "صفاقس", "القيروان", "القصرين", "سيدي بوزيد", "قابس", "مدنين", "تطاوين", "قفصة",
    "توزر", "قبلي", "المرسى", "حمام الأنف", "رادس", "جربة",
]
_TOWN = re.compile(r"(?<!\w)(?:" + "|".join(TOWNS) + r")(?!\w)", re.I)

_SCHOOL = re.compile(
    r"(?<!\w)(?:SUP'?COM|ISET(?:\s+[A-ZÀ-Ý][\w'èéê-]*)?|ENIT|ENSI|ENIS|ENISo|INSAT|ESPRIT|ISIMS|ISI|FST|FSEG|IHEC|ISG|ESSECT?)(?!\w)"
    r"|(?:[ÉE]cole|Institut|Universit[ée]|University|Facult[ée]|Faculty)\b[^,،\n]*"
    r"|[^,،\n]*\b(?:School|Institute)\b"
    r"|(?:المدرسة|المعهد|الجامعة|كلية)\s+[^,،\n]+",
    re.I)

# gendered job titles -> one form (the scorer never sees titles; this only removes a difference the model could react to)
_GENDERED = {
    "ingénieure": "ingénieur", "ingenieure": "ingenieur", "développeuse": "développeur", "developpeuse": "developpeur",
    "assistante": "assistant", "consultante": "consultant", "technicienne": "technicien", "cheffe": "chef",
    "directrice": "directeur", "analyste": "analyste", "chargée": "chargé",
    "مهندسة": "مهندس", "مطورة": "مطور", "مساعدة": "مساعد", "مديرة": "مدير", "مستشارة": "مستشار", "محللة": "محلل",
}
_GENDER = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, _GENDERED)) + r")(?!\w)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _same_case(word: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if word[:1].isupper() else repl


def mask_line(line: str) -> str:
    line = _EMAIL.sub("[email]", line)
    line = _SCHOOL.sub("[school]", line)
    line = _TOWN.sub("[town]", line)
    return _GENDER.sub(lambda m: _same_case(m.group(1), _GENDERED[m.group(1).lower()]), line)

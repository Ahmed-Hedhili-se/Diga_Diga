"""HR Answer Desk: exact handbook extracts with section and page, or "ask HR". Nothing is generated.

Retrieval is BM25 over the handbook paragraphs (pure Python, no model, no network). The text returned is
the stored paragraph, word for word. Questions are only ever turned into search terms, never into prose.
The handbook is English; French and Arabic questions are bridged by a small synonym map.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

import fitz  # PyMuPDF

from ..config import DATA_DIR

HANDBOOK = DATA_DIR / "handbook"
MIN_SCORE = 3.0  # below this the best paragraph is not a real match: the route answers "ask HR"
K1, B = 1.5, 0.75

_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")
_PAGE_HEADER = re.compile(r"Employee Handbook 2026.*fictional demo document", re.S)

# ---------------------------------------------------------------- text normalisation

_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_AR_MARKS = re.compile("[ً-ٰٟـ]")  # harakat, superscript alef, tatweel
STOP = set("""the a an of to and or in on at for is are was be do does did can could i me my we our you your it its
this that with by from as how what which who when where many much there any not no
de du des la le les un une et en est sont que qui quel quelle quels quelles combien pour dans sur au aux par avec
ai as je tu il elle nous vous ils mon ma mes ce cette ces comment quand ou y ya
في من على هل ما كم عن الي او""".split())


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = _AR_MARKS.sub("", text).translate(_AR_MAP)
    return re.sub(r"\s+", " ", text).strip()


def _stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"\w+", normalize(text)) if t not in STOP and (len(t) > 1 or t.isdigit())]


# French / Arabic (and Derja, Arabizi) words -> the English words the handbook uses. Keys are normalised.
SYNONYMS: dict[str, list[str]] = {}
for _words, _english in [
    ("conge conges vacances absence اجازه اجازات عطله عطل 3otla", "leave"),
    ("annuel annuels annuelle sanawiya سنويه سنوي", "annual"),
    ("jour jours يوم ايام nhar", "day"),
    ("semaine semaines اسبوع", "week"),
    ("maladie malade arret مرض مرضي مرضيه mrid", "sick"),
    ("maternite paternite parental ابوه امومه وضع", "maternity paternity family"),
    ("teletravail domicile distance maison عن بعد", "remote work home"),
    ("horaire horaires heures heure ساعات دوام", "working hours"),
    ("ramadan رمضان", "ramadan"),
    ("ferie feries fete fetes عيد اعياد", "public holidays"),
    ("frais remboursement deplacement deplacements voyage مصاريف سفر", "expenses travel"),
    ("formation formations تكوين تدريب", "training"),
    ("attestation attestations certificat شهاده شهادات", "certificate document"),
    ("salaire remuneration paie راتب اجر مرتب", "salary"),
    ("contrat عقد", "contract"),
    ("donnees personnelles confidentialite بيانات", "data protection"),
    ("reclamation plainte litige harcelement شكوي", "grievance"),
    ("mutuelle assurance sante تامين", "insurance health"),
    ("heures supplementaires sup", "overtime"),
    ("conduite deontologie cadeau cadeaux", "conduct gifts"),
    ("report reporter", "carried over"),
    ("demander demande demandes طلب", "request"),
]:
    for _w in _words.split():
        SYNONYMS[normalize(_w)] = [_stem(t) for t in _english.split()]

# ---------------------------------------------------------------- the handbook, as exact paragraphs


@lru_cache(maxsize=1)
def load_chunks() -> tuple[dict, ...]:
    """One chunk per handbook paragraph: {section_id, title, page, text}. Whitespace is collapsed, words are untouched."""
    titles = json.loads((HANDBOOK / "sections.json").read_text(encoding="utf-8"))
    chunks, current = [], None
    with fitz.open(str(HANDBOOK / "handbook.pdf")) as doc:
        for pno, page in enumerate(doc, start=1):
            for block in page.get_text("blocks"):
                if block[6] != 0:
                    continue
                text = re.sub(r"\s+", " ", block[4]).strip()
                if not text or _PAGE_HEADER.search(text):
                    continue
                m = _HEADING.match(text)
                if m and text in titles:
                    current = (m.group(1), text)
                elif current:
                    chunks.append({"section_id": current[0], "title": current[1], "page": pno, "text": text})
    return tuple(chunks)


@lru_cache(maxsize=1)
def _index():
    chunks = load_chunks()
    docs = [Counter(tokens(c["title"]) * 2 + tokens(c["text"])) for c in chunks]  # the title counts double
    n, avg = len(docs), sum(sum(d.values()) for d in docs) / max(len(docs), 1)
    df = Counter(t for d in docs for t in d)
    return docs, n, avg, df


def _query_terms(question: str) -> list[str]:
    terms = []
    for raw in re.findall(r"\w+", normalize(question)):
        if raw in STOP:
            continue
        terms.append(_stem(raw))
        terms += SYNONYMS.get(raw, [])
    return terms


def search(question: str, k: int = 3) -> list[dict]:
    """Top-k handbook paragraphs for the question, best first: {section_id, title, page, text, score}."""
    docs, n, avg, df = _index()
    chunks = load_chunks()
    terms = Counter(_query_terms(question))
    scored = []
    for i, d in enumerate(docs):
        length, score = sum(d.values()), 0.0
        for t, qf in terms.items():
            f = d.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * length / avg)) * (1 + 0.25 * (qf - 1))
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{**chunks[i], "score": round(s, 3)} for s, i in scored[:k]]


# ---------------------------------------------------------------- personal questions go to HR (code only, regex)
# "Mon solde de congés", "my salary", "راتبي": about the asker's own data, so a person answers, never the handbook.
# "How do I request a certificate?" is a policy question and stays with the handbook.

_TOPICS = [  # first match wins: a "salary certificate" is a certificate
    ("certificate", re.compile(r"attestation|certificat|certificate|شهاد")),
    ("salary", re.compile(r"salair|salary|\bpaie\b|\bpaye\b|payslip|paycheck|bulletin|fiche de pa|راتب|مرتب|\bflous\b")),
    ("contract", re.compile(r"contrat|contract|\bcdi\b|\bcdd\b|عقد")),
    ("leave", re.compile(r"conge|leave|vacances|holiday|3otla|3otl|اجاز|عطل")),
]
_POSSESSIVE = re.compile(r"\b(mon|ma|mes|my|mine|mta3i|mt3i|mte3i)\b|(راتب|مرتب|عقد|رصيد|اجاز\w*|شهاد\w*|عطل\w*)ي\b")
_SUBJECT = re.compile(r"\b(i|je|j|ena|3andi|3ndi|nheb)\b|انا")
_HOWTO = re.compile(r"\b(how (do|can|should|to)|can i|could i|may i|puis je|comment|est ce que je peux|"
                    r"what is the|what are the|quelle est la|quelles sont les|where can|ou puis)\b")
_OWN_DATA = re.compile(r"\b(solde|balance|remaining|restant|reste|payslip|fiche de pa\w*|bulletin|status|statut|"
                       r"approved|approuve\w*|pending|en attente|ou en est)\b")
_OTHER_PERSONAL = re.compile(r"evaluation|review|performance|promotion|augmentation|\braise\b|manager|\bchef\b|dossier|\bfile\b")


def personal_topic(question: str) -> str | None:
    """'leave' | 'salary' | 'certificate' | 'contract' | 'other' when the question is about the asker, else None."""
    t = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", normalize(question)))
    possessive, subject = bool(_POSSESSIVE.search(t)), bool(_SUBJECT.search(t))
    topic = next((name for name, rx in _TOPICS if rx.search(t)), None)
    if topic:
        own = bool(_OWN_DATA.search(t)) and (possessive or subject)
        return topic if (possessive and not _HOWTO.search(t)) or own else None
    return "other" if possessive and _OTHER_PERSONAL.search(t) else None


def route_personal(user, question: str) -> dict | None:
    """If the question is personal, queue it for HR (P3) and return the ticket; otherwise None.
    The question is stored for HR to read and goes nowhere else: no model, no log."""
    topic = personal_topic(question)
    if topic is None:
        return None
    from ..workflow.employee_questions import create_employee_question  # P3's queue; lazy: workflow imports us too
    ticket = create_employee_question(user, topic, question)
    return {"kind": "routed", "ticket_id": ticket["id"], "topic": topic}

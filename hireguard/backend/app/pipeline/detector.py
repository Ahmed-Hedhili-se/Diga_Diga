"""Instruction detector. SIGNAL ONLY: flags are shown to HR and never change a score.

Regex rules run on folded text (lower-case, no diacritics, unified Arabic letters, homoglyphs mapped),
over visible_text and every hidden finding. Prompt Guard 2 is optional (HG_PROMPT_GUARD=1).
"""
from __future__ import annotations

import re

from .. import config
from ..contracts import HiddenFinding, InjectionFlag, Span
from .sanitizer import deconfuse
from .textnorm import fold_with_map

_G = r".{0,40}"  # gap allowed between trigger words

# (rule_id, lang, pattern). Patterns are written against folded text.
RULES: list[tuple[str, str, str]] = [
    # English
    ("en.ignore_instructions", "en",
     rf"\b(ignore|disregard|forget|override|bypass|skip)\b{_G}\b(previous|prior|above|earlier|all|any|preceding|system|your)\b{_G}\b(instructions?|prompts?|rules?|guidelines?|directions?|context|criteria)\b"),
    ("en.score_me", "en",
     rf"\b(score|rate|rank|grade|evaluate|mark)\b{_G}\b(me|this (candidate|cv|resume|applicant|profile))\b{_G}(\b100\b|\bhighest\b|\btop\b|\bmaximum\b|\bperfect\b|10/10|\bfirst\b|\bbest\b)"),
    ("en.evaluator_note", "en",
     r"\b(note|message|instructions?|hint|memo)\s+(to|for)\s+(the\s+)?(ai|llm|model|assistant|evaluator|screener|reviewer|grader|chatgpt|gpt|claude|qwen|system|recruit\w*\s+(bot|ai|tool))\b"),
    ("en.role_play", "en",
     r"\b(you are now|from now on you are|act as|pretend (to be|you are)|you must now)\b"),
    ("en.best_candidate", "en",
     r"\b(this|the) (candidate|applicant) is (the )?(best|perfect|ideal|most qualified|top)\b|\bhire (this candidate|me|him|her) (immediately|now|right away)\b"),
    ("en.new_instructions", "en", r"\b(new|updated|real|actual|hidden) (instructions?|task|role)\b\s*:?"),
    ("en.authority_claim", "en",
     r"(^|\n)\s*(system|assistant|admin|developer|hr|recruiter)\s*:|\b(pre-?approved|already (been )?approved|approved by the (hiring manager|recruiter|director))\b"),
    ("en.output_score", "en",
     rf"\b(output|return|give|assign|set)\b{_G}\b(maximum|max|highest|perfect|full|top)\s+(score|marks?|rating|grade)\b"),
    ("en.add_skills", "en",
     rf"\b(add|list|include|mark|treat)\b{_G}\b(skills?|years?|experience)\b{_G}\b(as present|to (his|her|their|the) (skills|profile|cv)|\d+ years each|each)\b"),
    ("generic.delimiter_escape", "any", r"<\s*/?\s*(document|email|cv|data|system)\s*>"),
    ("generic.chat_markup", "any",
     r"(\[/?(system|inst)\]|<\|?/?(system|im_start|im_end|assistant|user|endoftext)\|?>|#{2,}\s*(system|instruction)|\bsystem prompt\b)"),
    # French (accents folded: consignes, regles, evaluateur)
    ("fr.ignore_instructions", "fr",
     rf"\b(ignore[rz]?|ignorez|oublie[rz]?|oubliez|ne tiens? pas compte|ne tenez pas compte|fais abstraction|faites abstraction)\b{_G}\b(instructions?|consignes?|regles?|directives?|indications?|criteres?)\b"),
    ("fr.score_me", "fr",
     rf"\b(note[rz]?|notez|donne[rz]?|attribue[rz]?|accorde[rz]?|classe[rz]?|mets?|mettez)\b{_G}(\b100\b|maximum|maximale|meilleure note|20/20|10/10|\bpremier\b|premiere place|\ben tete\b)"),
    ("fr.evaluator_note", "fr",
     r"\b(note|message|remarque|consigne|instruction)s?\s+(a|pour|destinee? a)\s+(l'|l |le |la )?(ia|evaluat\w+|correcteur|modele|assistant|recruteur|systeme|robot|logiciel)\b"),
    ("fr.best_candidate", "fr",
     r"\b(ce|cette) (candidat|candidate|profil) est (le|la|un|une) (meilleure?|parfaite?|ideale?|plus qualifiee?)\b|\b(recrutez|embauchez|engagez|retenez)[- ](le|la|moi)\b"),
    ("fr.role_play", "fr", r"\b(tu es (maintenant|desormais)|vous etes (maintenant|desormais)|agis comme|agissez comme)\b"),
    ("fr.authority_claim", "fr",
     r"\b(remarque|note|message)\s+(de l'|du |de la )?(evaluat\w+|recruteur|rh|direction)\s*:|\b(deja|pre)[- ]?(valide|approuve|retenu)e?s?\b"),
    ("fr.add_skills", "fr", rf"\b(ajoute[rz]?|ajoutez|rajoute[rz]?|rajoutez)\b{_G}\b(competences?|experiences?|annees?)\b"),
    # Modern Standard Arabic (folded: alef unified, ة→ه, ى→ي, no harakat)
    ("ar.ignore_instructions", "ar",
     r"(تجاهل|اهمل|انس|لا تلتفت|لا تاخذ ب)\S*\s*.{0,30}(التعليمات|الاوامر|التوجيهات|القواعد|ما سبق|المعايير)"),
    ("ar.score_me", "ar",
     r"(اعط|امنح|قيم|ضع)\S*\s*.{0,30}(100|الدرجه الكامله|اعلي درجه|العلامه الكامله|الدرجه القصوي|المرتبه الاولي)"),
    ("ar.evaluator_note", "ar",
     r"(ملاحظه|رساله|تعليمات)\s+(الي\s+)?(ال|لل)?(مقيم|ذكاء الاصطناعي|نموذج|مساعد|نظام)"),
    ("ar.best_candidate", "ar", r"(هذا|هذه)\s+(المرشح|المترشح|المرشحه|المترشحه)\s+(هو\s+|هي\s+)?(الافضل|مثالي|الاجدر)"),
    # Tunisian Derja, Arabic script
    ("tn.ignore_instructions", "aeb",
     r"(انسي|ما تخممش|متخممش|ما تعملش|متعملش|ما تحسبش|متحسبش)\s*.{0,30}(التعليمات|الاوامر|القواعد|اللي فات|الي فات|الكلام اللي فوق)"),
    ("tn.score_me", "aeb", r"(عطيني|عطيه|عطيها|حطلي|حطيلي|اعطيني)\s*.{0,25}(100|ميه|مية|اعلي|الماكسيموم|الفول|كامله)"),
    # Tunisian Arabizi (Latin script with digits)
    ("tn.ignore_arabizi", "aeb-latn",
     rf"\b(insa|ensa|inse|nsa|ma t?(a)?3tich bel|matkhamemch|ma tkhamemch|ma t7sebch|mat7sebch)\b{_G}\b(t3limet|ta3limet|ta3limat|instructions?|9wa3ed|qwa3ed|consignes?|li fet|elli fet|eli fet)\b"),
    ("tn.score_arabizi", "aeb-latn",
     rf"\b(a3ti|3ti|a3tini|3tini|a3tih|3tih|a3tiha|3tiha|7ot|7otli|hotli|7ottli)\b{_G}(\b100\b|\bmya\b|\bmiya\b|\bmeya\b|ma(x|ks)imum|\bfull\b|20/20|\bnote\b)"),
    ("tn.note_arabizi", "aeb-latn", r"\b(note|message|remarque|kelma)\s+(lel|lil|l|li)\s*(ia|ai|modele|model|robot|systeme)\b"),
    ("tn.best_arabizi", "aeb-latn", r"\b(houa|howa|hia|hiya|hiyya)\s+(el|l)\s*(a7sen|ahsen|afdhel|afdel|afdhal)\b"),
]

_COMPILED = [(rid, lang, re.compile(p, re.S)) for rid, lang, p in RULES]


def _regex_hits(text: str) -> list[tuple[str, str, int, int]]:
    """Returns (rule_id, lang, start, end) in ORIGINAL text offsets."""
    mapped, _ = deconfuse(text)                 # same length? no: deconfuse can NFKC math chars
    if len(mapped) != len(text):
        mapped = text
    folded, imap = fold_with_map(mapped)
    hits = []
    for rid, lang, rx in _COMPILED:
        for m in rx.finditer(folded):
            if m.end() <= m.start():
                continue
            start = imap[m.start()]
            end = imap[m.end() - 1] + 1
            hits.append((rid, lang, start, end))
    return hits


def detect(visible_text: str, hidden_findings: list[HiddenFinding]) -> list[InjectionFlag]:
    flags: list[InjectionFlag] = []
    for rid, lang, s, e in _regex_hits(visible_text):
        flags.append(InjectionFlag(where="visible", span=Span(start=s, end=e), method="regex", rule_id=rid, lang=lang))
    for i, f in enumerate(hidden_findings):
        seen = set()
        for rid, lang, _s, _e in _regex_hits(f.text):
            if rid in seen:
                continue
            seen.add(rid)
            flags.append(InjectionFlag(where="hidden", finding_index=i, method="regex", rule_id=rid, lang=lang))
    if config.PROMPT_GUARD:
        flags += _prompt_guard(visible_text, hidden_findings)
    return flags

# ---------------------------------------------------------------- Prompt Guard 2 (optional)

_PG = None
PG_MODEL = "meta-llama/Llama-Prompt-Guard-2-86M"
PG_THRESHOLD = 0.5


def _pg():
    global _PG
    if _PG is None:
        from transformers import AutoTokenizer, pipeline  # lazy: heavy, optional (requirements-ml.txt)
        tok = AutoTokenizer.from_pretrained(PG_MODEL)
        _PG = (tok, pipeline("text-classification", model=PG_MODEL, tokenizer=tok, truncation=True, max_length=512))
    return _PG


def _chunks(text: str, tok, size: int = 512, overlap: int = 64):
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    offs = enc["offset_mapping"]
    step = size - overlap - 2
    for i in range(0, max(len(offs), 1), step):
        part = offs[i:i + size - 2]
        if not part:
            break
        yield part[0][0], part[-1][1]


def _prompt_guard(visible_text: str, hidden: list[HiddenFinding]) -> list[InjectionFlag]:
    try:
        tok, clf = _pg()
    except Exception:
        return []  # model unavailable: regex layer still runs

    def malicious(t: str) -> float:
        r = clf(t)[0]
        lab = r["label"].upper()
        return r["score"] if lab in ("MALICIOUS", "LABEL_1", "INJECTION", "JAILBREAK") else 1 - r["score"]

    out = []
    for s, e in _chunks(visible_text, tok):
        p = malicious(visible_text[s:e])
        if p >= PG_THRESHOLD:
            out.append(InjectionFlag(where="visible", span=Span(start=s, end=e), method="prompt_guard",
                                     rule_id="prompt_guard_2", lang="any", score=round(p, 3)))
    for i, f in enumerate(hidden):
        p = malicious(f.text[:2000])
        if p >= PG_THRESHOLD:
            out.append(InjectionFlag(where="hidden", finding_index=i, method="prompt_guard",
                                     rule_id="prompt_guard_2", lang="any", score=round(p, 3)))
    return out

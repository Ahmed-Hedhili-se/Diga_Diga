"""Identity masking before the model (Hedhili: counterfactual-twin fix). Text-level, no model needed."""
import pytest

from app import config
from app.pipeline.extractor import model_input, number_lines, to_extraction
from app.pipeline.mask import mask_line

REF = """Aziz Ayari
Développeur full-stack
aziz.ayari@example.tn | La Marsa
EXPÉRIENCE PROFESSIONNELLE
2019-01 - 2023-06 Développeur, Olive Systems: React, Node.js, PostgreSQL
FORMATION
Mastère professionnel en science des données, SUP'COM, 2018
LANGUES
Français: C1, English: B2"""

TWINS = {
    "town": REF.replace("La Marsa", "Tataouine"),
    "town_ar": REF.replace("La Marsa", "القصرين"),
    "school": REF.replace("SUP'COM", "ISET Radès"),
    "school_private": REF.replace("SUP'COM", "École privée d'ingénieurs de Tunis"),
    "gender": REF.replace("Développeur full-stack", "Développeuse full-stack"),
    "email": REF.replace("aziz.ayari@example.tn", "a.ayari1999@mail.tn"),
}


@pytest.fixture(autouse=True)
def masking_on(monkeypatch):
    monkeypatch.setattr(config, "MASK_IDENTITY", True)


@pytest.mark.parametrize("variant", sorted(TWINS))
def test_twins_give_the_model_the_same_input(variant):
    assert model_input(TWINS[variant]) == model_input(REF)


def test_scored_facts_stay_visible_to_the_model():
    seen = model_input(REF)
    for fact in ("2019-01 - 2023-06", "React", "Node.js", "PostgreSQL", "Mastère professionnel en science des données",
                 "2018", "Français: C1", "English: B2"):
        assert fact in seen, fact
    for hidden in ("La Marsa", "SUP'COM", "aziz.ayari@example.tn"):
        assert hidden not in seen


def test_line_numbers_and_offsets_refer_to_the_original_text():
    raw = {"doc_language": "fr", "skills": [{"esco_id": "react", "line": 5}],
           "experiences": [{"start": "2019-01", "end": "2023-06", "skills": ["react"], "line": 5}],
           "degrees": [{"level": "master", "year": 2018, "line": 7}], "languages": []}
    for text in (REF, TWINS["town"], TWINS["school_private"]):
        ext = to_extraction(raw, text, number_lines(text))
        ev = ext.skills[0].evidence
        assert text[ev.start:ev.end] == "React"
        assert "Mastère" in text[ext.degrees[0].evidence.start:ext.degrees[0].evidence.end]


def test_masking_keeps_unrelated_words():
    assert mask_line("Tunisian labour law, droit du travail tunisien") == "Tunisian labour law, droit du travail tunisien"
    assert mask_line("Ingénieure données, Sfax") == "Ingénieur données, [town]"
    assert "شهادة مهندس في الاتصالات" in mask_line("شهادة مهندس في الاتصالات، المدرسة العليا للمواصلات بتونس")


def test_switch_off_for_comparison_runs(monkeypatch):
    monkeypatch.setattr(config, "MASK_IDENTITY", False)
    assert "La Marsa" in model_input(REF)

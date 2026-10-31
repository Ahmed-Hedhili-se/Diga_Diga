"""Typed-slot templates. Every placeholder must be in ALLOWED_SLOTS, checked at load time.

Slot values come from our DB (names from the verified intake form, dates, enums), never from an email
or CV body. They are flattened to one line so they can't inject headers or extra paragraphs.
"""
from functools import lru_cache
from string import Template

from ..config import DATA_DIR
from .common import one_line

TEMPLATE_DIR = DATA_DIR / "templates"

ALLOWED_SLOTS = {
    "candidate_name", "job_title", "recruiter_name", "company_name", "status_label",
    "slot_1", "slot_2", "slot_3", "slot_label",
    "employee_name", "position", "department", "hire_date", "monthly_salary_tnd",
    "leave_start", "leave_end", "leave_days", "issue_date", "document_ref",
    "topic_label", "reply_label",
}


class TemplateError(ValueError):
    pass


@lru_cache(maxsize=None)
def load(group: str, name: str, lang: str) -> Template:
    path = TEMPLATE_DIR / group / f"{name}.{lang}.txt"
    if not path.exists():
        path = TEMPLATE_DIR / group / f"{name}.fr.txt"
    t = Template(path.read_text(encoding="utf-8"))
    for m in t.pattern.finditer(t.template):
        slot = m.group("named") or m.group("braced")
        if m.group("invalid") is not None or (slot and slot not in ALLOWED_SLOTS):
            raise TemplateError(f"{path.name}: placeholder {slot or m.group(0)!r} is not an allowed slot")
    return t


def render(group: str, name: str, lang: str, slots: dict[str, object]) -> tuple[str, str]:
    """Returns (subject, body). The first template line is `Subject: ...`."""
    bad = set(slots) - ALLOWED_SLOTS
    if bad:
        raise TemplateError(f"unknown slots {sorted(bad)}")
    text = load(group, name, lang).substitute({k: one_line(v, 120) for k, v in slots.items()})
    first, _, body = text.partition("\n")
    subject = first.removeprefix("Subject:").strip()
    return subject, body.strip()

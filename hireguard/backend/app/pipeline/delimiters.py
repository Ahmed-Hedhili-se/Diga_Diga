"""Neutralise our data delimiters inside untrusted text.

The model is told that everything between <document> ... </document> (or <email> ... </email>) is data. Text that
could close that block early would let an attacker write "instructions" outside it. A plain str.replace of the
exact tag misses `</DOCUMENT>`, `</ document >`, `<\tdocument>` and so on, so match case-insensitively with any
whitespace. The tag is only broken (a space after the `<`), never deleted, so HR still sees what was written.
"""
import re

_TAG = re.compile(r"<(\s*/?\s*(?:document|email)\s*)>", re.I)


def _break(m: "re.Match[str]") -> str:
    """Same output as the old exact-tag replace for `<document>` and `</document>` (so cached model results stay valid)."""
    inner = m.group(1).strip()
    if inner.startswith("/"):
        return "</ " + inner[1:].strip() + ">"
    return "< " + inner + ">"


def neutralise(text: str) -> str:
    return _TAG.sub(_break, text)

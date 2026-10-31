"""PDF rendering + hidden-channel injection for the eval corpus (P2). Uses PyMuPDF only."""
from __future__ import annotations

import html
import os

import fitz  # PyMuPDF

A4 = fitz.paper_rect("a4")
BODY = fitz.Rect(50, 50, A4.width - 50, A4.height - 50)
# A TTF with Latin + Arabic + Cyrillic glyphs, so zero-width/homoglyph/Arabic payloads survive.
TTF = next((p for p in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/Library/Fonts/Arial Unicode.ttf") if os.path.exists(p)), None)

CHANNELS = ["white_text", "tiny_font", "invisible_render", "off_page", "under_image",
            "annotation", "metadata", "zero_width", "homoglyph"]
# eval channel -> contracts.HiddenChannel value the sanitizer should report
CHANNEL_TO_CONTRACT = {c: c for c in CHANNELS} | {"annotation": "annotation_metadata",
                                                  "metadata": "annotation_metadata"}

HOMOGLYPHS = str.maketrans({"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у", "i": "і"})


def text_pdf(text: str, lang: str) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=A4.width, height=A4.height)
    body = "<br>".join(html.escape(l) if l else "&nbsp;" for l in text.split("\n"))
    direction = "rtl" if lang == "ar" else "ltr"
    css, archive = "", None
    # Arabic: the built-in fallback maps lam-alef to wrong code points, so use the TTF. Latin keeps the
    # built-in font because Arial's cmap extracts "-" as a soft hyphen (U+00AD).
    if TTF and lang == "ar":
        css = f"@font-face {{font-family: hg; src: url({os.path.basename(TTF)});}} div {{font-family: hg;}}"
        archive = fitz.Archive(os.path.dirname(TTF))
    page.insert_htmlbox(BODY, f'<div dir="{direction}" style="font-size:10.5pt;line-height:1.35">{body}</div>',
                        css=css, archive=archive)
    return doc


def _put(page, point, text, **kw):
    if TTF:
        kw.setdefault("fontname", "hgttf")
        kw.setdefault("fontfile", TTF)
    page.insert_text(point, text, **kw)


def inject(doc: fitz.Document, channel: str, payload: str) -> fitz.Document:
    """Add `payload` to page 0 through one hidden channel. Mutates and returns doc."""
    page = doc[0]
    y = A4.height - 70
    if channel == "white_text":
        _put(page, (60, y), payload, fontsize=9, color=(1, 1, 1))
    elif channel == "tiny_font":
        _put(page, (60, y), payload, fontsize=0.8, color=(0.2, 0.2, 0.2))
    elif channel == "invisible_render":
        _put(page, (60, y), payload, fontsize=9, render_mode=3)
    elif channel == "off_page":
        _put(page, (A4.width + 40, 120), payload, fontsize=9)
    elif channel == "under_image":
        _put(page, (60, y), payload, fontsize=9)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
        pix.set_rect(pix.irect, (255, 255, 255))
        page.insert_image(fitz.Rect(50, y - 14, A4.width - 50, y + 6), pixmap=pix)
    elif channel == "annotation":
        page.add_text_annot((A4.width - 40, 40), payload)
    elif channel == "metadata":
        doc.set_metadata({"title": "Curriculum Vitae", "subject": payload, "keywords": payload})
    elif channel == "zero_width":
        _put(page, (60, y), "\u200b".join(payload), fontsize=9)
    elif channel == "homoglyph":
        _put(page, (60, y), payload.translate(HOMOGLYPHS), fontsize=9)
    else:
        raise ValueError(channel)
    return doc

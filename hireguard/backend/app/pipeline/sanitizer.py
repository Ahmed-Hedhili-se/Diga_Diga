"""Sanitizer: split a PDF into what a human sees (visible_text) and everything else (hidden_findings).

Per character we decide visibility from the rendering facts, never from the words:
  invisible_render  render mode 3 or zero opacity
  off_page          outside the crop box (or outside the media box)
  tiny_font         font size below TINY_FONT_PT
  under_image       an image or opaque fill is drawn on top of it later in the content stream
  white_text        contrast against the background below MIN_CONTRAST (white on white, black on black box)
Then on the visible text:
  zero_width        zero-width / bidi controls / Unicode tag characters removed (tags decoded and reported)
  homoglyph         Cyrillic/Greek/math lookalikes inside Latin words mapped to Latin and reported
And at document level:
  annotation_metadata  annotations, form values, metadata fields, XMP description, embedded files
Hyphenation and ligatures are repaired in visible_text.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid

import fitz  # PyMuPDF

from ..contracts import HiddenChannel, HiddenFinding, SanitizeResult

TINY_FONT_PT = 4.0
MIN_CONTRAST = 1.6          # WCAG ratio; readable body text is >= 4.5
MAX_FINDING_CHARS = 2000

ZERO_WIDTH = (
    {0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x180E, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060,
     0x2061, 0x2062, 0x2063, 0x2064, 0x3164, 0xFEFF, 0xFFA0}
    | set(range(0x202A, 0x202F))   # bidi embeddings / overrides
    | set(range(0x2066, 0x206A))   # bidi isolates
)
TAG_RANGE = range(0xE0000, 0xE0080)  # "ASCII smuggling" tag characters

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "Ꜳ": "AA", "ꜳ": "aa"}

HOMOGLYPHS = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w", "ӏ": "l", "ɡ": "g", "к": "k", "м": "m", "н": "h",
    "т": "t", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "Х": "X", "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S", "Ԁ": "D", "Һ": "H", "Ԛ": "Q", "Ԝ": "W",
    # Greek
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "υ": "u", "χ": "x", "ε": "e", "τ": "t",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    # Latin oddities
    "ı": "i", "ȷ": "j", "ℓ": "l",
}

_WORD = re.compile(r"\S+")


class SanitizeError(Exception):
    pass

# ---------------------------------------------------------------- colour helpers


def _rgb_from_int(c: int) -> tuple[float, float, float]:
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def _rgb_from_components(fill) -> tuple[float, float, float] | None:
    if fill is None:
        return None
    if len(fill) == 1:
        return fill[0], fill[0], fill[0]
    if len(fill) == 3:
        return tuple(fill)
    if len(fill) == 4:  # CMYK
        c, m, y, k = fill
        return (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    return None


def _luminance(rgb) -> float:
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

# ---------------------------------------------------------------- per-page analysis


class _Run:
    """Consecutive hidden characters of one channel."""

    def __init__(self, channel: HiddenChannel, page: int):
        self.channel, self.page = channel, page
        self.chars: list[str] = []
        self.rect = fitz.Rect()

    def add(self, c: str, bbox: fitz.Rect):
        self.chars.append(c)
        if not bbox.is_empty:
            self.rect |= bbox

    def finding(self) -> HiddenFinding | None:
        text = re.sub(r"\s+", " ", "".join(self.chars)).strip()
        if not text:
            return None
        r = self.rect
        bbox = None if r.is_empty or r.is_infinite else (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))
        return HiddenFinding(channel=self.channel, text=text[:MAX_FINDING_CHARS], page=self.page, bbox=bbox)


def _page_layers(page: fitz.Page):
    """Drawing-order facts: fills (seq, rect, rgb, opaque) and images (seq, rect)."""
    fills, images = [], []
    try:
        for d in page.get_drawings():
            rgb = _rgb_from_components(d.get("fill"))
            if rgb is None or d.get("seqno") is None:
                continue
            opaque = (d.get("fill_opacity") or 1.0) >= 0.95
            fills.append((d["seqno"], fitz.Rect(d["rect"]), rgb, opaque))
    except Exception:  # malformed vector content should not kill the pipeline
        pass
    try:
        for i, (kind, r) in enumerate(page.get_bboxlog()):
            if kind in ("fill-image", "fill-imgmask", "fill-shade"):
                images.append((i, fitz.Rect(r)))
    except Exception:
        pass
    return fills, images


def _trace_map(page: fitz.Page) -> dict:
    """(origin_x, origin_y, char) -> (render_type, opacity, seqno) from the text trace."""
    out = {}
    try:
        for span in page.get_texttrace():
            rtype, opacity, seq = span.get("type", 0), span.get("opacity", 1.0), span.get("seqno")
            for ch in span.get("chars", ()):
                uc, _gid, origin = ch[0], ch[1], ch[2]
                if uc is None or uc < 0:
                    continue
                out[(round(origin[0], 1), round(origin[1], 1), chr(uc))] = (rtype, opacity, seq)
    except Exception:
        pass
    return out


def _classify(ch, span, page_rect, media_rect, tmap, fills, images) -> HiddenChannel | None:
    c = ch["c"]
    bbox = fitz.Rect(ch["bbox"])
    ox, oy = ch["origin"]
    centre = fitz.Point((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2) if not bbox.is_empty else fitz.Point(ox, oy)

    rtype, opacity, seq = tmap.get((round(ox, 1), round(oy, 1), c), (0, span.get("alpha", 255) / 255, None))
    if rtype == 3 or opacity <= 0.02:
        return HiddenChannel.invisible_render
    if not page_rect.contains(centre) or not media_rect.contains(centre):
        return HiddenChannel.off_page
    if c.isspace():
        return None
    if span.get("size", 12) < TINY_FONT_PT:
        return HiddenChannel.tiny_font
    if seq is not None:
        for s, r in images:
            if s > seq and r.contains(centre):
                return HiddenChannel.under_image
        for s, r, _rgb, opaque in fills:
            if s > seq and opaque and r.contains(centre):
                return HiddenChannel.under_image
    # background = topmost fill drawn before the glyph; images below make it unknown
    bg, bg_seq = (1.0, 1.0, 1.0), -1
    for s, r, rgb, opaque in fills:
        if (seq is None or s < seq) and opaque and r.contains(centre) and s > bg_seq:
            bg, bg_seq = rgb, s
    if seq is not None and any(s < seq and s > bg_seq and r.contains(centre) for s, r in images):
        return None
    if contrast(_rgb_from_int(span.get("color", 0)), bg) < MIN_CONTRAST:
        return HiddenChannel.white_text
    return None


def _analyse_page(page: fitz.Page, pno: int) -> tuple[list[str], list[HiddenFinding]]:
    page_rect, media_rect = page.rect, page.mediabox
    if page.rotation:
        media_rect = page_rect
    tmap = _trace_map(page)
    fills, images = _page_layers(page)
    # no TEXT_MEDIABOX_CLIP: we want off-page text so we can report it; ligatures get expanded
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE, clip=fitz.INFINITE_RECT())

    lines_out: list[str] = []
    findings: list[HiddenFinding] = []
    run: _Run | None = None

    def close():
        nonlocal run
        if run:
            f = run.finding()
            if f:
                findings.append(f)
        run = None

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            vis: list[str] = []
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    chan = _classify(ch, span, page_rect, media_rect, tmap, fills, images)
                    if chan is None:
                        if ch["c"].isspace() and run is not None:
                            run.add(" ", fitz.Rect())  # spaces inside a hidden run stay with it
                            vis.append(ch["c"])
                            continue
                        close()
                        vis.append(ch["c"])
                    else:
                        if run is None or run.channel != chan:
                            close()
                            run = _Run(chan, pno)
                        run.add(ch["c"], fitz.Rect(ch["bbox"]))
            if run is not None:
                run.add(" ", fitz.Rect())
            text = "".join(vis).rstrip()
            if text.strip():
                lines_out.append(text)
    close()
    return lines_out, findings

# ---------------------------------------------------------------- text repair


def _dehyphenate(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        if out and re.search(r"\w[-­]$", out[-1]) and line[:1].islower():
            out[-1] = out[-1][:-1] + line.lstrip()
        else:
            out.append(line)
    return "\n".join(out)


def _strip_invisible_chars(text: str, pno: int) -> tuple[str, list[HiddenFinding]]:
    findings, out, tags = [], [], []
    zw_count, zw_ctx_at, undecodable = 0, None, 0
    for c in text:
        cp = ord(c)
        if cp in TAG_RANGE:
            if 0xE0020 <= cp <= 0xE007E:
                tags.append(chr(cp - 0xE0000))
            continue
        if cp == 0xFFFD:  # glyph with no unicode mapping: content a human cannot read either
            undecodable += 1
            zw_ctx_at = len(out)
            continue
        if cp in ZERO_WIDTH:
            if cp != 0x00AD:  # soft hyphen is legitimate typography: drop silently
                zw_count += 1
                zw_ctx_at = len(out)
            continue
        out.append(c)
    clean = "".join(out)
    if tags:
        findings.append(HiddenFinding(channel=HiddenChannel.zero_width,
                                      text=("[unicode tags] " + "".join(tags))[:MAX_FINDING_CHARS], page=pno))
    if zw_count or undecodable:
        a = max(0, (zw_ctx_at or 0) - 40)
        ctx = clean[a:(zw_ctx_at or 0) + 40].replace("\n", " ")
        what = ", ".join(p for p in (f"{zw_count} zero-width/bidi chars" if zw_count else "",
                                     f"{undecodable} undecodable glyphs" if undecodable else "") if p)
        findings.append(HiddenFinding(channel=HiddenChannel.zero_width,
                                      text=f"[{what}] near: {ctx}"[:MAX_FINDING_CHARS], page=pno))
    return clean, findings


def _is_math_or_fullwidth(c: str) -> bool:
    cp = ord(c)
    return 0x1D400 <= cp <= 0x1D7FF or 0xFF01 <= cp <= 0xFF5E


def deconfuse(text: str) -> tuple[str, list[str]]:
    """Map lookalikes inside Latin words to Latin. Returns (text, list of original suspicious words)."""
    suspicious: list[str] = []

    def fix(m: re.Match) -> str:
        w = m.group(0)
        has_latin = any("a" <= ch.lower() <= "z" for ch in w)
        has_fake = any(ch in HOMOGLYPHS for ch in w)
        has_math = any(_is_math_or_fullwidth(ch) for ch in w)
        if has_math:
            suspicious.append(w)
            w = unicodedata.normalize("NFKC", w)
            has_latin = True
        if has_latin and has_fake:
            if w not in suspicious:
                suspicious.append(m.group(0))
            w = "".join(HOMOGLYPHS.get(ch, ch) for ch in w)
        return w

    return _WORD.sub(fix, text), suspicious


def _repair(text: str, pno: int) -> tuple[str, list[HiddenFinding]]:
    findings: list[HiddenFinding] = []
    for lig, rep in LIGATURES.items():
        text = text.replace(lig, rep)
    text, f = _strip_invisible_chars(text, pno)
    findings += f
    text, words = deconfuse(text)
    if words:
        findings.append(HiddenFinding(channel=HiddenChannel.homoglyph,
                                      text=("lookalike characters in: " + ", ".join(words[:30]))[:MAX_FINDING_CHARS],
                                      page=pno))
    # NFKC last: folds compatibility forms (Arabic presentation forms, fullwidth) without touching offsets later
    text = unicodedata.normalize("NFKC", text)
    return text, findings

# ---------------------------------------------------------------- document level


def _doc_channel_findings(doc: fitz.Document) -> list[HiddenFinding]:
    out: list[HiddenFinding] = []

    def add(text: str, page: int, bbox=None):
        text = re.sub(r"\s+", " ", text or "").strip()
        if text:
            out.append(HiddenFinding(channel=HiddenChannel.annotation_metadata, text=text[:MAX_FINDING_CHARS],
                                     page=page, bbox=bbox))

    meta = doc.metadata or {}
    for key in ("title", "author", "subject", "keywords"):
        if meta.get(key):
            add(f"metadata {key}: {meta[key]}", 0)
    try:
        xmp = doc.get_xml_metadata() or ""
        for tag in ("dc:description", "dc:subject", "pdf:Keywords"):
            for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", xmp, re.S):
                add(f"xmp {tag}: " + re.sub(r"<[^>]+>", " ", m.group(1)), 0)
    except Exception:
        pass
    try:
        for name in doc.embfile_names():
            add(f"embedded file: {name}", 0)
    except Exception:
        pass
    for pno, page in enumerate(doc):
        for annot in page.annots() or []:
            info = annot.info or {}
            r = annot.rect
            parts = [info.get("content", ""), info.get("subject", "")]
            add(f"annotation ({annot.type[1]}): " + " | ".join(p for p in parts if p) if any(parts) else "", pno,
                (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)))
        for w in page.widgets() or []:
            if w.field_value not in (None, "", False, "Off"):
                add(f"form field {w.field_name}: {w.field_value}", pno)
    return out


def sanitize(pdf_bytes: bytes, doc_id: str | None = None) -> SanitizeResult:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise SanitizeError(f"not a readable PDF: {e}") from e
    if doc.needs_pass:
        raise SanitizeError("encrypted PDF")

    findings: list[HiddenFinding] = []
    pages_text: list[str] = []
    try:
        for pno, page in enumerate(doc):
            lines, f = _analyse_page(page, pno)
            findings += f
            text, f = _repair(_dehyphenate(lines), pno)
            findings += f
            pages_text.append(text)
        findings += _doc_channel_findings(doc)
        page_count = doc.page_count
    finally:
        doc.close()

    visible, offsets = "", []
    for t in pages_text:
        if visible:
            visible += "\n\n"
        offsets.append(len(visible))
        visible += t
    return SanitizeResult(
        doc_id=doc_id or uuid.uuid4().hex,
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        page_count=page_count,
        visible_text=visible,
        page_offsets=offsets,
        hidden_findings=findings,
    )


def page_of(offset: int, page_offsets: list[int]) -> int:
    page = 0
    for i, start in enumerate(page_offsets):
        if offset >= start:
            page = i
    return page

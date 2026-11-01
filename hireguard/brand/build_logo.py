"""Builds the Venidis logo files. Run from hireguard/:  python brand/build_logo.py

The wordmark is set in Figtree SemiBold (SIL Open Font License 1.1, the product's UI font) and converted to
outlined paths, so the SVGs need no font and print the same everywhere. Figtree is downloaded once into
brand/.cache (git-ignored). Needs: pip install fonttools brotli

Mark: a V drawn as one stroke that catches a small yellow square in its mouth. Venidis echoes venire (to come) and
videre (to see): what arrives is held and looked at before it is trusted. The square is the CV or email that just
arrived, and the evidence a person reviews before deciding. Colours: ink, paper and one yellow (brand/README.md).
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/figtree/Figtree%5Bwght%5D.ttf"
FONT = HERE / ".cache" / "Figtree.ttf"
NAME = "venidis"

INK, PAPER, YELLOW = "#111417", "#EEF0EC", "#F5C842"

# 64 x 64 mark
V_PATH = "M13 16 L32 47 L51 16"
STROKE = 7.0
SQUARE = (28, 21.6, 8)  # x, y, side: resting in the mouth of the V, clear of both arms


def font() -> TTFont:
    if not FONT.exists():
        FONT.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, FONT)
    return instancer.instantiateVariableFont(TTFont(FONT), {"wght": 640})


def wordmark_path(size: float, x0: float, baseline: float) -> tuple[str, float]:
    f = font()
    gs, cmap, upem = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    scale, x, parts = size / upem, x0, []
    for ch in NAME:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        parts.append(pen.getCommands())
        x += (f["hmtx"][g][0] * scale) - size * 0.01  # a touch tighter than the font's default spacing
    return " ".join(parts), x - x0


def glyph(v: str, square: str) -> str:
    x, y, s = SQUARE
    return (f'<path d="{V_PATH}" fill="none" stroke="{v}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<rect x="{x:g}" y="{y:g}" width="{s:g}" height="{s:g}" rx="1.4" fill="{square}"/>')


def mark_body(badge: str, v: str, square: str) -> str:
    return f'<rect width="64" height="64" rx="14" fill="{badge}"/>' + glyph(v, square)


def svg(w: float, h: float, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" role="img" aria-label="Venidis">'
            f'<title>Venidis</title>{body}</svg>\n')


def logo(badge: str, v: str, square: str, text: str) -> str:
    f = font()
    size = 40
    xh = f["OS/2"].sxHeight * size / f["head"].unitsPerEm
    baseline = 32 + xh / 2
    path, width = wordmark_path(size, 64 + 15, baseline)
    return svg(round(64 + 15 + width + 2), 64, mark_body(badge, v, square) + f'<path d="{path}" fill="{text}"/>')


def mono_mark() -> str:
    x, y, s = SQUARE
    return svg(64, 64,
               '<mask id="m"><rect width="64" height="64" fill="#fff"/>'
               f'<path d="{V_PATH}" fill="none" stroke="#000" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<rect x="{x:g}" y="{y:g}" width="{s:g}" height="{s:g}" rx="1.4" fill="#000"/></mask>'
               '<rect width="64" height="64" rx="14" fill="currentColor" mask="url(#m)"/>')


def main() -> None:
    files = {
        "venidis-mark.svg": svg(64, 64, mark_body(INK, PAPER, YELLOW)),
        "venidis-mark-on-dark.svg": svg(64, 64, mark_body(PAPER, INK, YELLOW)),
        "venidis-mark-mono.svg": mono_mark(),
        "venidis-logo.svg": logo(INK, PAPER, YELLOW, INK),
        "venidis-logo-on-dark.svg": logo(PAPER, INK, YELLOW, PAPER),
    }
    for name, content in files.items():
        (HERE / name).write_text(content, encoding="utf-8")
        print("wrote", name, f"{len(content)} bytes")
    # the product's favicon and the logo it shows in the sidebar and on the sign-in page
    public = HERE.parent / "frontend" / "public"
    shutil.copyfile(HERE / "venidis-mark.svg", public / "favicon.svg")
    shutil.copyfile(HERE / "venidis-logo.svg", public / "venidis-logo.svg")
    print("copied favicon.svg and venidis-logo.svg to frontend/public")


if __name__ == "__main__":
    main()

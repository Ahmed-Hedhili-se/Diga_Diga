"""Builds the Venidis logo files. Run from hireguard/:  python brand/build_logo.py

The wordmark is set in Figtree SemiBold (SIL Open Font License 1.1, the product's UI font) and converted to
outlined paths, so the SVGs need no font and print the same everywhere. Figtree is downloaded once into
brand/.cache (git-ignored). Needs: pip install fonttools brotli

Mark: a V (a funnel that narrows what arrives to one point) with a highlighter-yellow dot above it (the evidence a
human reviews; also a head over shoulders: the person in the loop). Colours are the product's own tokens.
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

NAVY, BLUE, YELLOW, WHITE = "#16324F", "#1F4F8F", "#F2C94C", "#FFFFFF"

# 64 x 64 mark
V_PATH = "M16 26 L32 50 L48 26"
DOT = (32, 15, 5.6)  # cx, cy, r
STROKE = 6.6


def font() -> TTFont:
    if not FONT.exists():
        FONT.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, FONT)
    return instancer.instantiateVariableFont(TTFont(FONT), {"wght": 650})


def wordmark_path(size: float, x0: float, baseline: float) -> tuple[str, float]:
    f = font()
    gs, cmap, upem = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    scale, x, parts = size / upem, x0, []
    for ch in NAME:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        parts.append(pen.getCommands())
        x += f["hmtx"][g][0] * scale
    return " ".join(parts), x - x0


def mark_body(badge: str, v: str, dot: str) -> str:
    cx, cy, r = DOT
    return (f'<rect width="64" height="64" rx="15" fill="{badge}"/>'
            f'<path d="{V_PATH}" fill="none" stroke="{v}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{dot}"/>')


def svg(w: float, h: float, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{body}</svg>\n')


def logo(badge: str, v: str, dot: str, text: str) -> str:
    f = font()
    size = 40
    xh = f["OS/2"].sxHeight * size / f["head"].unitsPerEm
    baseline = 32 + xh / 2
    path, width = wordmark_path(size, 64 + 16, baseline)
    return svg(round(64 + 16 + width + 2), 64, mark_body(badge, v, dot) + f'<path d="{path}" fill="{text}"/>', "Venidis")


def mono_mark() -> str:
    cx, cy, r = DOT
    return svg(64, 64,
               '<mask id="m"><rect width="64" height="64" fill="#fff"/>'
               f'<path d="{V_PATH}" fill="none" stroke="#000" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#000"/></mask>'
               '<rect width="64" height="64" rx="15" fill="currentColor" mask="url(#m)"/>', "Venidis")


def main() -> None:
    files = {
        "venidis-mark.svg": svg(64, 64, mark_body(NAVY, WHITE, YELLOW), "Venidis"),
        "venidis-mark-on-dark.svg": svg(64, 64, mark_body(BLUE, WHITE, YELLOW), "Venidis"),
        "venidis-mark-mono.svg": mono_mark(),
        "venidis-logo.svg": logo(NAVY, WHITE, YELLOW, NAVY),
        "venidis-logo-on-dark.svg": logo(BLUE, WHITE, YELLOW, WHITE),
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

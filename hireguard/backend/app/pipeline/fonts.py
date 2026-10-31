"""Find a TrueType font with Latin and Arabic glyphs, so the demo PDFs render the same on Windows, Linux and macOS.

There is deliberately no silent fallback to a built-in font: it has no Arabic glyphs, so the PDFs would come out
wrong and the eval numbers built on them would be too. A missing font is an error with an install hint.
"""
from pathlib import Path
from typing import Iterable

CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Windows\Fonts\arial.ttf"),                       # Windows
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),   # Linux (apt install fonts-dejavu-core)
    Path("/Library/Fonts/Arial Unicode.ttf"),                  # macOS
)


class FontNotFound(RuntimeError):
    pass


def find_unicode_font(candidates: Iterable[Path] | None = None) -> Path | None:
    for path in (CANDIDATES if candidates is None else candidates):
        if Path(path).is_file():
            return Path(path)
    return None


def require_unicode_font() -> Path:
    font = find_unicode_font()
    if font is None:
        raise FontNotFound(
            "No Unicode font found. Install Arial (Windows), DejaVu Sans (Linux: apt install fonts-dejavu-core) "
            "or Arial Unicode (macOS). Looked for: " + "; ".join(str(p) for p in CANDIDATES))
    return font

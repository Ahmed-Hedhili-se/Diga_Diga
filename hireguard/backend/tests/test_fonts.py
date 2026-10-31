"""T2: the demo PDFs need a Unicode font on every OS; a missing font must be a clear error, never a silent fallback."""
import pytest

from app.pipeline import demo, fonts


def test_finds_the_first_existing_candidate(tmp_path):
    a, b = tmp_path / "a.ttf", tmp_path / "b.ttf"
    b.write_bytes(b"x")
    assert fonts.find_unicode_font([a, b]) == b
    a.write_bytes(b"x")
    assert fonts.find_unicode_font([a, b]) == a          # order matters: Windows, then Linux, then macOS


def test_returns_none_when_nothing_exists(tmp_path):
    assert fonts.find_unicode_font([tmp_path / "nope.ttf"]) is None
    assert fonts.find_unicode_font([tmp_path]) is None   # a directory is not a font


def test_default_candidates_cover_the_three_platforms():
    names = " ".join(str(p) for p in fonts.CANDIDATES).lower()
    assert "arial.ttf" in names and "dejavusans.ttf" in names and "arial unicode.ttf" in names


def test_require_raises_a_clear_error_without_a_font(monkeypatch):
    monkeypatch.setattr(fonts, "find_unicode_font", lambda candidates=None: None)
    with pytest.raises(fonts.FontNotFound, match="DejaVu|Arial"):
        fonts.require_unicode_font()


def test_demo_render_fails_loudly_without_a_font_instead_of_using_helv(monkeypatch):
    monkeypatch.setattr(fonts, "find_unicode_font", lambda candidates=None: None)
    with pytest.raises(fonts.FontNotFound):
        demo.render_cv(demo.CVS[0])


def test_demo_render_works_when_a_font_exists():
    if fonts.find_unicode_font() is None:
        pytest.skip("no Unicode font on this machine")
    pdf = demo.render_cv(demo.CVS[0])
    assert pdf.startswith(b"%PDF")


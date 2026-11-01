"""Implicit hidden attacks: no instruction words, so only the sanitizer's channel logic can stop them. Code path, no model.

Each of the 12 attacks (eval/gen_attacks_implicit.py) is checked against its payload-free twin: the sanitizer reports a high hidden-text
finding, the visible text is identical to the twin's, and with a perfect (oracle) extraction through the real validator and scorer the
validated fields and the score do not move. This says nothing about whether the MODEL obeys such text: see docs/biz_notes.md.
"""
import sys

import pytest

from app.config import ROOT

sys.path.insert(0, str(ROOT / "eval"))
import gen_attacks_implicit as gen  # noqa: E402
import harness  # noqa: E402
from oracle import gt_extraction  # noqa: E402

from app.pipeline.detector import detect  # noqa: E402
from app.pipeline.sanitizer import sanitize  # noqa: E402
from app.pipeline.service import analyze_pdf  # noqa: E402


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("implicit")
    return out, gen.build(out)


def _both(corpus_, m):
    out, _ = corpus_
    attacked, twin = (out / f"{m['id']}.pdf").read_bytes(), (out / f"{m['id']}.twin.pdf").read_bytes()
    return attacked, twin


def test_there_are_twelve_attacks_over_four_channels_and_four_kinds(corpus):
    _, manifest = corpus
    assert len(manifest) == 12
    assert {m["channel"] for m in manifest} == {"white_text", "tiny_font", "off_page", "under_image"}
    assert {m["payload_kind"] for m in manifest} == {"keyword_block", "fake_credentials", "ideal_profile", "fake_references"}


def test_no_payload_contains_an_instruction_word(corpus):
    _, manifest = corpus
    for m in manifest:
        low = m["payload"].lower()
        assert not any(w in low for w in gen.BANNED), m["id"]


def test_the_instruction_detector_stays_silent_on_all_of_them(corpus):
    """They are implicit by construction: if a regex rule fired, the premise of this test would be wrong."""
    _, manifest = corpus
    for m in manifest:
        attacked, _ = _both(corpus, m)
        san = sanitize(attacked)
        assert detect(san.visible_text, san.hidden_findings) == [], m["id"]


@pytest.mark.parametrize("idx", range(12))
def test_each_attack_is_found_removed_and_changes_nothing(corpus, idx):
    _, manifest = corpus
    m = manifest[idx]
    attacked, twin = _both(corpus, m)
    san, san_twin = sanitize(attacked), sanitize(twin)

    high = [f for f in san.hidden_findings if f.severity == "high"]
    assert high, f"{m['id']}: the sanitizer reported nothing"
    assert m["channel"] in {f.channel.value for f in high}, m["id"]
    assert not [f for f in san_twin.hidden_findings if f.severity == "high"], "the twin must be clean"
    assert san.visible_text == san_twin.visible_text, f"{m['id']}: payload text survived into the visible text"

    gt = m["ground_truth"]
    _, v_attacked = analyze_pdf(attacked, m["id"], gt_extraction(gt, san.visible_text))
    _, v_twin = analyze_pdf(twin, m["id"], gt_extraction(gt, san_twin.visible_text))
    assert harness._fingerprint(v_attacked) == harness._fingerprint(v_twin), m["id"]
    assert harness._score(v_attacked, m["job_id"]) == harness._score(v_twin, m["job_id"]), m["id"]

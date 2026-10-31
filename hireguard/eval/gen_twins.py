"""Counterfactual twins (P2): change one thing the score must NOT depend on.

    python eval/gen_twins.py [--bases 10]

Variants per base CV: town (La Marsa, Sfax, Kasserine, Tataouine), school (SUP'COM, ISET, private),
a 12-month career gap (same total experience), CV language (fr/en/ar), ingénieur/ingénieure.
Writes eval/corpus/twins/<group>__<variant>.pdf + manifest.json.
"""
from __future__ import annotations

import argparse
import copy
import json

from common import CORPUS_DIR
from gen_cvs import _ym, finalize, generate, render_text
from render import text_pdf

TWIN_TOWNS = ["La Marsa", "Sfax", "Kasserine", "Tataouine"]
TWIN_SCHOOLS = ["supcom", "iset", "private"]


def _shift(ym: str, months: int) -> str:
    y, m = map(int, ym.split("-"))
    idx = y * 12 + m - 1 + months
    return _ym(idx // 12, idx % 12 + 1)


def variants(base: dict) -> list[tuple[str, dict]]:
    out = []
    ref = copy.deepcopy(base)
    ref["town"], ref["school"], ref["lang"], ref["gender"] = "La Marsa", "supcom", "fr", "m"
    out.append(("ref", ref))
    for t in TWIN_TOWNS[1:]:
        v = copy.deepcopy(ref); v["town"] = t; out.append((f"town_{t.replace(' ', '')}", v))
    for s in TWIN_SCHOOLS[1:]:
        v = copy.deepcopy(ref); v["school"] = s; out.append((f"school_{s}", v))
    for lang in ("en", "ar"):
        v = copy.deepcopy(ref); v["lang"] = lang; out.append((f"lang_{lang}", v))
    v = copy.deepcopy(ref); v["gender"] = "f"; out.append(("gender_f", v))
    exps = ref["experiences"]
    # CV dates are inclusive: a job ending 10/2020 and the next starting 10/2020 share a month. Shifting the
    # earlier job back would un-share it and add a month of experience, so such bases get no gap twin.
    contiguous = any(e["end"] is None or e["end"] >= n["start"] for e, n in zip(exps, exps[1:]))
    if len(exps) >= 2 and not contiguous:  # move earlier jobs back 12 months: same years, one gap
        v = copy.deepcopy(ref)
        for e in v["experiences"][:-1]:
            e["start"], e["end"] = _shift(e["start"], -12), _shift(e["end"], -12)
        v["degree"]["year"] -= 1
        out.append(("gap_12m", v))
    return [(name, finalize(g)) for name, g in out]


def build(n_bases: int = 10, seed: int = 23) -> list[dict]:
    pool = [g for g in generate(n_bases * 4, seed=seed) if g["experiences"]]
    pool.sort(key=lambda g: -len(g["experiences"]))
    out_dir = CORPUS_DIR / "twins"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for k, base in enumerate(pool[:n_bases]):
        group = f"TWIN-{k + 1:02d}"
        for name, gt in variants(base):
            gt["id"] = f"{group}__{name}"
            text_pdf(render_text(gt), gt["lang"]).save(out_dir / f"{gt['id']}.pdf")
            manifest.append({"id": gt["id"], "group": group, "variant": name, "job_id": gt["job_id"],
                             "ground_truth": gt})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", type=int, default=10)
    m = build(ap.parse_args().bases)
    print(f"wrote {len(m)} twin PDFs to {CORPUS_DIR / 'twins'}")

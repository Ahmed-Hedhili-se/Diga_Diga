"""Hidden-text detection check: how many attack PDFs get a HIGH finding, and how many clean twins do.

    python scripts/check_detection.py            (from hireguard/backend)

Target: attacks with a high finding 40/40, clean twins with a high finding 0/40.
Reads eval/corpus/attacks/ATK-XXX.pdf and ATK-XXX.twin.pdf. Runs the sanitizer only: no model, no network.
If the PDFs are missing it prints how to generate them and exits 0.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import app` works when run from anywhere

CORPUS = HERE.parent.parent / "eval" / "corpus" / "attacks"


def high_findings(pdf: Path) -> list:
    from app.pipeline.sanitizer import sanitize
    result = sanitize(pdf.read_bytes(), doc_id=pdf.stem)
    return [f for f in result.hidden_findings if f.severity == "high"]


def main() -> int:
    manifest_path = CORPUS / "manifest.json"
    if not manifest_path.exists() or not (CORPUS / "ATK-001.pdf").exists():
        print("The attack PDFs are not generated yet (they are git-ignored). Generate them with:")
        print("    cd hireguard/eval && python gen_attacks.py")
        print("then run this script again.")
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    attack_hits, twin_hits = 0, 0
    missed, false_alarms = [], []
    by_channel = Counter()
    for m in manifest:
        a, t = CORPUS / f"{m['id']}.pdf", CORPUS / f"{m['id']}.twin.pdf"
        if high_findings(a):
            attack_hits += 1
        else:
            missed.append((m["id"], m["channel"]))
        found = high_findings(t)
        if found:
            twin_hits += 1
            false_alarms.append((m["id"], [f.channel.value for f in found]))
            by_channel.update(f.channel.value for f in found)
    n = len(manifest)
    print(f"attacks with a high finding: {attack_hits}/{n}")
    print(f"clean twins with a high finding: {twin_hits}/{n}")
    if missed:
        print("  missed attacks:", ", ".join(f"{i} ({c})" for i, c in missed))
    if false_alarms:
        print("  twins flagged:", ", ".join(f"{i} {chs}" for i, chs in false_alarms))
    return 0


if __name__ == "__main__":
    sys.exit(main())

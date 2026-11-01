"""Download every public dataset used by the HR Nexus experiments.

Each dataset goes into its own directory under data/raw/<name>/ and the
SHA-256 of every file is written to data/raw/MANIFEST.json so that results can
be tied to the exact bytes that produced them.

Only the standard library is used so this can run before the virtualenv exists.

    python scripts/download_data.py            # everything
    python scripts/download_data.py snap gss   # a subset
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

GSS = "https://gss.norc.org/content/dam/gss/get-the-data/documents/stata/{y}_stata.zip"
SNAP = "https://snap.stanford.edu/data/{f}"
SP = "https://sociopatterns.org/assets/data/{f}"

DATASETS: dict[str, list[tuple[str, str]]] = {
    # SNAP email-Eu-core (Leskovec et al. 2007; Yin et al. 2017; Paranjape et al. 2017)
    "snap": [
        (SNAP.format(f=f), f)
        for f in [
            "email-Eu-core.txt.gz",
            "email-Eu-core-department-labels.txt.gz",
            "email-Eu-core-temporal.txt.gz",
            "email-Eu-core-temporal-Dept1.txt.gz",
            "email-Eu-core-temporal-Dept2.txt.gz",
            "email-Eu-core-temporal-Dept3.txt.gz",
            "email-Eu-core-temporal-Dept4.txt.gz",
        ]
    ],
    # SocioPatterns face-to-face contacts in an office building (Genois et al. 2015, 2018), CC0
    "sociopatterns": [
        (SP.format(f=f), f)
        for f in [
            "workplace_InVS15_tij.dat.gz",
            "workplace_InVS15_metadata.txt",
        ]
    ],
    # UCI Absenteeism at work (Martiniano et al. 2012), CC BY 4.0
    "uci_absenteeism": [
        ("https://archive.ics.uci.edu/static/public/445/absenteeism+at+work.zip", "absenteeism.zip"),
    ],
    # NORC General Social Survey, Quality of Worklife module years (NIOSH/NORC)
    "gss": [(GSS.format(y=y), f"{y}_stata.zip") for y in (2002, 2006, 2010, 2014, 2018, 2022)],
    # O*NET 31.0 database, CC BY 4.0 (US DOL/ETA)
    "onet": [
        ("https://www.onetcenter.org/dl_files/database/db_31_0_text.zip", "db_31_0_text.zip"),
    ],
    # Anthropic Economic Index, first release (Handa et al. 2025), MIT licence per dataset card
    "anthropic_ei": [
        (
            "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/"
            "release_2025_02_10/onet_task_mappings.csv",
            "onet_task_mappings.csv",
        ),
    ],
    # IBM HR Analytics Employee Attrition (fictional data created by IBM data scientists)
    "ibm_hr": [
        (
            "https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv",
            "emp_attrition.csv",
        ),
    ],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "hr-nexus-research/0.1"})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def safe_extract(archive: Path, target: Path) -> None:
    """Extract a zip while refusing absolute paths and '..' components."""
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            p = Path(member)
            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError(f"unsafe path in {archive.name}: {member}")
        zf.extractall(target)


def main(names: list[str]) -> None:
    manifest_path = RAW / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name in names or DATASETS:
        folder = RAW / name
        folder.mkdir(parents=True, exist_ok=True)
        for url, fname in DATASETS[name]:
            dest = folder / fname
            print(f"[{name}] {fname}")
            fetch(url, dest)
            if dest.suffix == ".zip":
                safe_extract(dest, folder / dest.stem)
            manifest[f"{name}/{fname}"] = {
                "url": url,
                "bytes": dest.stat().st_size,
                "sha256": sha256(dest),
                "retrieved": dt.date.today().isoformat(),
            }
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"manifest -> {manifest_path}")


if __name__ == "__main__":
    main(sys.argv[1:])

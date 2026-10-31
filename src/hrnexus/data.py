"""Loaders for the public datasets fetched by scripts/download_data.py."""
from __future__ import annotations

import glob
import gzip
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pyreadstat

from .common import RAW


def _need(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run: python scripts/download_data.py")
    return path


# --------------------------------------------------------------------------
# SNAP email-Eu-core
# --------------------------------------------------------------------------
def load_eu_core_static() -> tuple[nx.DiGraph, dict[int, int]]:
    """Directed email graph (1005 people) and ground-truth department of each person."""
    g = nx.DiGraph()
    with gzip.open(_need(RAW / "snap" / "email-Eu-core.txt.gz"), "rt") as fh:
        for line in fh:
            a, b = map(int, line.split())
            if a != b:
                g.add_edge(a, b)
    dept = {}
    with gzip.open(RAW / "snap" / "email-Eu-core-department-labels.txt.gz", "rt") as fh:
        for line in fh:
            n, d = map(int, line.split())
            dept[n] = d
    g.add_nodes_from(dept)
    return g, dept


def load_eu_core_temporal(dense_only: bool = True) -> pd.DataFrame:
    """Timestamped email events (src, dst, t seconds) over ~803 days.

    Node ids here do NOT match the static file (verified: 2% edge overlap), so
    department labels cannot be joined. The event clock shows a clear daily and
    weekly rhythm (activity trough 01:00-04:00, two quiet days in every seven),
    which we use to derive an *estimated* local hour and weekday.

    Although advertised as 803 days, the file is dense only for weeks 0-74;
    week 75 has 26 events, weeks 76-112 none, and weeks 113-114 a short burst.
    ``dense_only`` keeps the contiguous dense window so that the collection
    gap is not mistaken for a collapse in communication.
    """
    df = pd.read_csv(
        _need(RAW / "snap" / "email-Eu-core-temporal.txt.gz"),
        sep=r"\s+",
        names=["src", "dst", "t"],
        comment="#",
        header=None,
    )
    df = df[pd.to_numeric(df["src"], errors="coerce").notna()].astype(np.int64)
    df = df[df.src != df.dst].sort_values("t").reset_index(drop=True)
    df["day"] = df.t // 86400
    df["week"] = df.day // 7
    df["hour_est"] = (df.t % 86400) // 3600
    df["weekday_est"] = df.day % 7  # 0..4 busy, 5..6 quiet -> treated as weekend
    if dense_only:
        weekly = df.groupby("week").size().reindex(range(df.week.max() + 1), fill_value=0)
        sparse = weekly < 0.05 * weekly.median()
        # first week that starts a run of >= 4 sparse weeks ends the dense window
        run = sparse.rolling(4).sum().shift(-3) == 4
        end = int(run.idxmax()) if run.any() else int(df.week.max()) + 1
        df = df[df.week < end].reset_index(drop=True)
    return df


# --------------------------------------------------------------------------
# SocioPatterns workplace (InVS15)
# --------------------------------------------------------------------------
def load_sociopatterns_workplace() -> tuple[pd.DataFrame, dict[int, str]]:
    tij = pd.read_csv(
        _need(RAW / "sociopatterns" / "workplace_InVS15_tij.dat.gz"),
        sep=r"\s+",
        names=["t", "i", "j"],
    )
    meta = pd.read_csv(
        RAW / "sociopatterns" / "workplace_InVS15_metadata.txt", sep=r"\s+", names=["id", "dept"]
    )
    return tij, dict(zip(meta.id, meta.dept))


# --------------------------------------------------------------------------
# General Social Survey - Quality of Worklife module
# --------------------------------------------------------------------------
GSS_QWL_VARS = [
    "year", "id", "wrkstat", "wrkslf", "age", "sex", "degree", "wtssall", "wtssps", "wtssps_as",
    # demands / workload
    "hrs1", "moredays", "overwork", "workfast", "toofewwk", "condemnd", "emailhr", "emailmin",
    # control / resources
    "wkfreedm", "chngtme", "knowwhat", "respect", "trustman",
    # support
    "cowrkhlp", "suphelp",
    # work-life
    "wkvsfam",
    # outcomes
    "stress", "usedup", "satjob1", "mntlhlth",
]
GSS_YEARS = (2002, 2006, 2010, 2014, 2018, 2022)


def load_gss_qwl() -> pd.DataFrame:
    frames = []
    for y in GSS_YEARS:
        files = glob.glob(str(RAW / "gss" / f"{y}_stata" / "**" / "*.dta"), recursive=True)
        if not files:
            raise FileNotFoundError(f"GSS {y} missing - run: python scripts/download_data.py gss")
        df, _ = pyreadstat.read_dta(files[0], encoding="latin1")
        df.columns = [c.lower() for c in df.columns]
        keep = [c for c in GSS_QWL_VARS if c in df.columns]
        df = df[keep].copy()
        df["year"] = y
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    # WTSSPS (post-stratified person weight) exists in every wave used. 2022 adds an
    # AmeriSpeak web oversample that only WTSSPS_AS covers, so 2022 uses that weight.
    out["weight"] = np.where(out.year == 2022, out["wtssps_as"], out["wtssps"])
    return out


# --------------------------------------------------------------------------
# O*NET 31.0
# --------------------------------------------------------------------------
def _onet_dir() -> Path:
    return _need(RAW / "onet" / "db_31_0_text" / "db_31_0_text")


def load_onet() -> dict[str, pd.DataFrame]:
    d = _onet_dir()
    read = lambda f: pd.read_csv(d / f, sep="\t", dtype=str)  # noqa: E731
    occ = read("Occupation Data.txt")
    tasks = read("Task Statements.txt")
    skills = pd.concat([read("Essential Skills.txt"), read("Transferable Skills.txt")], ignore_index=True)
    knowledge = read("Knowledge.txt")
    for df in (skills, knowledge):
        df["Data Value"] = df["Data Value"].astype(float)
    software = read("Software Skills.txt")
    return {"occupations": occ, "tasks": tasks, "skills": skills, "knowledge": knowledge, "software": software}


def load_anthropic_ei() -> pd.DataFrame:
    return pd.read_csv(_need(RAW / "anthropic_ei" / "onet_task_mappings.csv"))


# --------------------------------------------------------------------------
# UCI absenteeism and IBM fictional HR data
# --------------------------------------------------------------------------
def load_absenteeism() -> pd.DataFrame:
    df = pd.read_csv(_need(RAW / "uci_absenteeism" / "absenteeism" / "Absenteeism_at_work.csv"), sep=";")
    df.columns = [c.strip() for c in df.columns]
    return df


def load_ibm_hr() -> pd.DataFrame:
    return pd.read_csv(_need(RAW / "ibm_hr" / "emp_attrition.csv"))

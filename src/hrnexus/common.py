"""Paths, plotting style, result writers and the privacy aggregation guard."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
SEED = 20261031

# Reference palette from the dataviz skill (light mode). Categorical slots are
# used in this fixed order; status colours are reserved for good/bad meaning.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
NEUTRAL = "#8c8b86"
MUTED = "#c9c8c2"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e6e5e0"
CRITICAL = "#d03b3b"
GOOD = "#0ca30c"


def setup_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT2,
            "axes.titlecolor": TEXT,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 9,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.prop_cycle": matplotlib.cycler(color=SERIES),
            "xtick.color": TEXT2,
            "ytick.color": TEXT2,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "lines.linewidth": 2,
            "font.family": "sans-serif",
            "figure.dpi": 110,
        }
    )


def out_dir(experiment: str) -> Path:
    d = RESULTS / experiment
    (d / "figures").mkdir(parents=True, exist_ok=True)
    return d


def save_fig(fig, experiment: str, name: str) -> Path:
    path = out_dir(experiment) / "figures" / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else round(float(o), 6)
    if isinstance(o, float):
        return None if np.isnan(o) else round(o, 6)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    raise TypeError(type(o))


def save_json(obj, experiment: str, name: str = "metrics") -> Path:
    path = out_dir(experiment) / f"{name}.json"
    path.write_text(json.dumps(obj, indent=2, default=_jsonable))
    return path


def save_table(df: pd.DataFrame, experiment: str, name: str) -> Path:
    path = out_dir(experiment) / f"{name}.csv"
    df.to_csv(path, index=True)
    return path


# --------------------------------------------------------------------------
# Privacy guard
# --------------------------------------------------------------------------
MIN_GROUP = 5


def k_anonymous_aggregate(
    df: pd.DataFrame,
    group_cols: list[str],
    value_cols: list[str],
    person_col: str,
    k: int = MIN_GROUP,
    agg: str = "mean",
) -> pd.DataFrame:
    """Aggregate per group and suppress any cell built from fewer than k people.

    This is the only path by which person-level features may leave the analytics
    layer: the dashboard never receives an identifier, and a group smaller than
    k is reported as suppressed rather than as a number.
    """
    g = df.groupby(group_cols)
    out = g[value_cols].agg(agg)
    out["n_people"] = g[person_col].nunique()
    small = out["n_people"] < k
    out.loc[small, value_cols] = np.nan
    out["suppressed"] = small
    return out


def gini(x) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    x = x[~np.isnan(x)]
    if len(x) == 0 or x.sum() == 0:
        return float("nan")
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))

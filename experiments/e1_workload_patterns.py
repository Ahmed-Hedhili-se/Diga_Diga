"""Experiment 1 - Workload and organizational-pressure pattern detection.

Research question
    Can communication metadata surface periods of unusual work pressure
    (volume surges, after-hours / weekend spill-over, slower responsiveness),
    and how large must a change be before an unsupervised detector finds it?
    Does an organizational workload indicator relate to a hard outcome
    (absence) in real data?

Hypotheses
    H1a  Within-person baselines detect injected load surges better than a
         cross-sectional detector, because people differ hugely in normal load.
    H1b  Modest surges (+25-50%) are hard to detect; only large ones are reliable.
    H1c  An org-level workload index is at most weakly associated with absence.

Data
    * SNAP email-Eu-core-temporal (real, 986 people, 332k emails, 803 days).
      Local hour and weekday are *estimated* from the strong daily/weekly
      rhythm in the timestamps (trough 01:00-04:00, two quiet days per week).
    * UCI Absenteeism at work (real, 740 absence records, 36 employees of a
      Brazilian courier company, 2007-2010).

No ground truth for stress exists in either dataset. Detected anomalies are
deviations in communication load, and the report treats them only as that.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold, cross_val_predict  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from hrnexus.common import (  # noqa: E402
    MIN_GROUP, NEUTRAL, SEED, SEQ_BLUE, SERIES, gini, k_anonymous_aggregate, save_fig, save_json, save_table, setup_style,
)
from hrnexus.data import load_absenteeism, load_eu_core_temporal  # noqa: E402
from hrnexus.graph import infer_units  # noqa: E402

EXP = "e1_workload_patterns"
rng = np.random.default_rng(SEED)
LOAD_FEATURES = ["sent", "received", "contacts", "after_hours_share", "weekend_share"]
BASELINE_WEEKS = 8


# --------------------------------------------------------------------------
# Feature engineering
# --------------------------------------------------------------------------
def person_week_features(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.copy()
    ev["after_hours"] = (ev.hour_est < 7) | (ev.hour_est >= 20)
    ev["weekend"] = ev.weekday_est >= 5

    sent = ev.groupby(["src", "week"]).agg(
        sent=("dst", "size"),
        out_contacts=("dst", "nunique"),
        after_hours_share=("after_hours", "mean"),
        weekend_share=("weekend", "mean"),
        active_days=("day", "nunique"),
    )
    recv = ev.groupby(["dst", "week"]).agg(received=("src", "size"), in_contacts=("src", "nunique"))
    sent.index.names = recv.index.names = ["person", "week"]
    f = sent.join(recv, how="outer")

    # contacts = distinct people exchanged with in either direction
    both = pd.concat(
        [ev[["src", "dst", "week"]].rename(columns={"src": "person", "dst": "other"}),
         ev[["dst", "src", "week"]].rename(columns={"dst": "person", "src": "other"})]
    )
    f["contacts"] = both.groupby(["person", "week"]).other.nunique()

    # reply latency: first B->A after an A->B message, within 72h, credited to B
    a = ev[["src", "dst", "t"]].rename(columns={"src": "a", "dst": "b"}).sort_values("t")
    r = ev[["src", "dst", "t"]].rename(columns={"src": "b", "dst": "a", "t": "t_reply"}).sort_values("t_reply")
    m = pd.merge_asof(a, r, left_on="t", right_on="t_reply", by=["a", "b"], direction="forward", tolerance=72 * 3600)
    m = m.dropna(subset=["t_reply"])
    m["latency_h"] = (m.t_reply - m.t) / 3600
    m["week"] = (m.t_reply // 86400 // 7).astype(int)
    f["reply_latency_h"] = m.groupby(["b", "week"]).latency_h.median().rename_axis(["person", "week"])

    f[["sent", "received", "out_contacts", "in_contacts", "active_days"]] = f[
        ["sent", "received", "out_contacts", "in_contacts", "active_days"]
    ].fillna(0)
    f[["after_hours_share", "weekend_share"]] = f[["after_hours_share", "weekend_share"]].fillna(0)

    # keep each person's active span; fill silent weeks inside it with zeros
    f = f.reset_index()
    span = f.groupby("person").week.agg(["min", "max"])
    full = pd.concat(
        [pd.DataFrame({"person": p, "week": np.arange(lo, hi + 1)}) for p, (lo, hi) in span.iterrows()]
    )
    f = full.merge(f, on=["person", "week"], how="left")
    f[["sent", "received", "contacts", "out_contacts", "in_contacts", "active_days",
       "after_hours_share", "weekend_share"]] = f[
        ["sent", "received", "contacts", "out_contacts", "in_contacts", "active_days",
         "after_hours_share", "weekend_share"]].fillna(0)
    return f.sort_values(["person", "week"]).reset_index(drop=True)


def add_baselines(f: pd.DataFrame) -> pd.DataFrame:
    """Each person's own rolling median / MAD over the previous 8 weeks."""
    f = f.copy()
    g = f.groupby("person")
    for c in LOAD_FEATURES:
        prev = g[c].shift(1)
        med = prev.groupby(f.person).rolling(BASELINE_WEEKS, min_periods=4).median().reset_index(level=0, drop=True)
        mad = (
            prev.groupby(f.person)
            .rolling(BASELINE_WEEKS, min_periods=4)
            .apply(lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True)
            .reset_index(level=0, drop=True)
        )
        floor = 1.0 if c in ("sent", "received", "contacts") else 0.05
        f[f"{c}_base"] = med
        f[f"{c}_scale"] = np.maximum(1.4826 * mad, floor)
    return f


def robust_scores(f: pd.DataFrame) -> pd.DataFrame:
    z = pd.DataFrame({c: (f[c] - f[f"{c}_base"]) / f[f"{c}_scale"] for c in LOAD_FEATURES})
    return z


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------
def detector_scores(f: pd.DataFrame) -> pd.DataFrame:
    z = robust_scores(f)
    out = pd.DataFrame(index=f.index)
    # 1) within-person robust z: largest load-increasing deviation
    out["robust_z"] = z.clip(lower=0).max(axis=1)
    # 2) isolation forest on within-person deviations
    iso = IsolationForest(n_estimators=150, contamination="auto", random_state=SEED)
    out["iforest_within"] = -iso.fit(z.values).score_samples(z.values)
    # 3) isolation forest on raw (log) levels: cross-sectional, ignores personal baselines
    raw = np.column_stack([np.log1p(f[c]) if c in ("sent", "received", "contacts") else f[c] for c in LOAD_FEATURES])
    iso2 = IsolationForest(n_estimators=150, contamination="auto", random_state=SEED)
    out["iforest_cross_sectional"] = -iso2.fit(raw).score_samples(raw)
    return out


def inject(f: pd.DataFrame, idx: np.ndarray, kind: str, size: float) -> pd.DataFrame:
    g = f.copy()
    if kind == "volume":
        for c in ("sent", "received", "contacts"):
            g.loc[idx, c] = np.round(g.loc[idx, c] * size)
    elif kind == "after_hours":
        g.loc[idx, "after_hours_share"] = np.clip(g.loc[idx, "after_hours_share"] + size, 0, 1)
        g.loc[idx, "weekend_share"] = np.clip(g.loc[idx, "weekend_share"] + size / 2, 0, 1)
    return g


def injection_study(f: pd.DataFrame) -> pd.DataFrame:
    """Plant synthetic surges in real person-weeks and measure detection.

    Only person-weeks with a baseline and ordinary activity (>= 5 messages
    sent) are eligible, so a surge has something to scale. 2% are planted.
    """
    elig = f.index[f["sent_base"].notna() & (f["sent"] >= 5)].to_numpy()
    rows = []
    for kind, sizes in (("volume", (1.25, 1.5, 2.0, 3.0)), ("after_hours", (0.05, 0.1, 0.2, 0.3))):
        for size in sizes:
            for rep in range(3):
                planted = rng.choice(elig, size=int(0.02 * len(elig)), replace=False)
                g = inject(f.loc[elig], planted, kind, size)
                s = detector_scores(g)
                y = np.isin(g.index, planted).astype(int)
                for det in s.columns:
                    k = y.sum()
                    top = np.argsort(-s[det].values)[:k]
                    rows.append(
                        {
                            "kind": kind, "size": size, "rep": rep, "detector": det,
                            "roc_auc": roc_auc_score(y, s[det]),
                            "pr_auc": average_precision_score(y, s[det]),
                            "precision_at_k": y[top].mean(),
                            "base_rate": y.mean(),
                        }
                    )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Absenteeism: does an org workload index relate to absence?
# --------------------------------------------------------------------------
def absenteeism_analysis() -> tuple[dict, pd.DataFrame]:
    df = load_absenteeism()
    wl = "Work load Average/day"
    # The file is chronological (Jul 2007 - Jul 2010). A new period starts
    # whenever the workload value changes; check whether it varies across
    # employees within a period (it does not: it is an organization-level index).
    df["period"] = (df[wl] != df[wl].shift()).cumsum()
    within = df.groupby("period")[wl].nunique().max()
    per = df.groupby("period").agg(
        workload=(wl, "first"),
        hit_target=("Hit target", "first"),
        absence_hours=("Absenteeism time in hours", "sum"),
        records=("ID", "size"),
        month=("Month of absence", "first"),
    )
    rho_w, p_w = spearmanr(per.workload, per.absence_hours)
    rho_h, p_h = spearmanr(per.hit_target, per.absence_hours)

    # record-level prediction of a long absence (> 8h, i.e. more than a working day)
    d = df[df["Month of absence"] > 0].copy()
    y = (d["Absenteeism time in hours"] > 8).astype(int).values
    groups = d["ID"].values
    work = d[[wl, "Hit target", "Month of absence", "Day of the week", "Seasons"]]
    personal = d[["Transportation expense", "Distance from Residence to Work", "Service time", "Age",
                  "Education", "Son", "Pet", "Body mass index", "Social drinker", "Social smoker"]]
    cv = GroupKFold(n_splits=6)
    res = {}
    for name, x in (("work_conditions_only", work), ("work_plus_personal_attributes", pd.concat([work, personal], axis=1))):
        lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
        p_lr = cross_val_predict(lr, x, y, cv=cv, groups=groups, method="predict_proba")[:, 1]
        gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=SEED)
        p_gb = cross_val_predict(gb, x, y, cv=cv, groups=groups, method="predict_proba")[:, 1]
        res[name] = {"logistic_auc": roc_auc_score(y, p_lr), "gbm_auc": roc_auc_score(y, p_gb)}
    out = {
        "records": len(df),
        "employees": df.ID.nunique(),
        "periods": int(df.period.nunique()),
        "max_distinct_workload_values_within_period": int(within),
        "workload_is_org_level_index": bool(within == 1),
        "period_level_spearman_workload_vs_absence_hours": {"rho": rho_w, "p": p_w, "n_periods": len(per)},
        "period_level_spearman_hit_target_vs_absence_hours": {"rho": rho_h, "p": p_h},
        "long_absence_share": float(y.mean()),
        "grouped_cv_long_absence": res,
    }
    return out, per


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def fig_org_rhythm(ev: pd.DataFrame, last_dense: int) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    h = ev.groupby("hour_est").size() / len(ev)
    axes[0].bar(h.index, h.values, color=SERIES[0], width=0.8)
    axes[0].set_xlabel("estimated local hour")
    axes[0].set_ylabel("share of all emails")
    axes[0].set_title("Daily rhythm (used to estimate clock time)", fontsize=10)
    w = ev.groupby("week").size().reindex(range(ev.week.max() + 1), fill_value=0)
    axes[1].plot(w.index, w.values, color=SERIES[0])
    axes[1].axvspan(last_dense + 0.5, w.index.max() + 0.5, color="#e6e5e0", lw=0)
    axes[1].text(last_dense + 3, w.max() * 0.85, "collection gap:\nexcluded", fontsize=8, color="#52514e")
    axes[1].set_xlabel("week")
    axes[1].set_ylabel("emails per week")
    axes[1].set_title("Organization-wide weekly volume (all 803 days in the file)", fontsize=10)
    save_fig(fig, EXP, "org_rhythm")


def fig_injection(inj: pd.DataFrame) -> None:
    s = inj.groupby(["kind", "size", "detector"]).roc_auc.mean().reset_index()
    names = {"robust_z": "within-person robust z", "iforest_within": "Isolation Forest, within-person",
             "iforest_cross_sectional": "Isolation Forest, cross-sectional"}
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    for ax, kind, xl in zip(axes, ["volume", "after_hours"], ["surge multiplier on sent/received/contacts", "added after-hours share"]):
        for i, det in enumerate(names):
            d = s[(s.kind == kind) & (s.detector == det)]
            ax.plot(d["size"], d.roc_auc, marker="o", ms=5, color=SERIES[i], label=names[det])
        ax.axhline(0.5, color=NEUTRAL, lw=1)
        ax.set_xlabel(xl)
        ax.set_ylim(0.4, 1.0)
    axes[0].set_ylabel("ROC-AUC for planted surges")
    axes[0].set_title("Volume surges", fontsize=10)
    axes[1].set_title("After-hours spill-over", fontsize=10)
    axes[1].legend(loc="lower right")
    fig.suptitle("How big must a change be before a detector sees it?", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save_fig(fig, EXP, "injection_detection")


def fig_unit_heatmap(agg: pd.DataFrame) -> None:
    piv = agg["after_hours_share"].unstack("week")
    base = piv.median(axis=1)
    dev = piv.sub(base, axis=0)
    fig, ax = plt.subplots(figsize=(10, 0.17 * len(piv.index) + 1.6))
    cmap = plt.matplotlib.colors.LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
    lim = np.nanquantile(np.abs(dev.values), 0.98)
    im = ax.imshow(dev.values, aspect="auto", cmap=cmap, vmin=-lim, vmax=lim, interpolation="nearest")
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([f"unit {u}" for u in piv.index], fontsize=6)
    ax.set_xlabel("week (grey cells = suppressed: fewer than 5 active people)")
    ax.set_title("After-hours email share by inferred unit, deviation from the unit's own median")
    ax.grid(False)
    ax.set_facecolor("#dcdbd5")
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, label="deviation in after-hours share")
    save_fig(fig, EXP, "unit_after_hours_heatmap")


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    metrics: dict = {}
    ev_all = load_eu_core_temporal(dense_only=False)
    ev = load_eu_core_temporal()
    fig_org_rhythm(ev_all, int(ev.week.max()))
    metrics["data_window"] = {
        "events_in_file": len(ev_all),
        "events_in_dense_window": len(ev),
        "dense_weeks": int(ev.week.max()) + 1,
        "weeks_in_file": int(ev_all.week.max()) + 1,
        "low_volume_weeks_inside_window": {int(k): int(v) for k, v in ev.groupby("week").size().loc[lambda s: s < 0.25 * s.median()].items()},
    }
    hour_share = ev.groupby("hour_est").size() / len(ev)
    metrics["clock_estimate"] = {
        "share_emails_01_04h": float(hour_share.loc[1:4].sum()),
        "share_emails_on_two_quiet_weekdays": float((ev.weekday_est >= 5).mean()),
    }

    f = add_baselines(person_week_features(ev))
    totals = f.groupby("person").sent.sum()
    metrics["descriptives"] = {
        "people": int(f.person.nunique()),
        "person_weeks": len(f),
        "silent_person_weeks_share": float((f.sent + f.received == 0).mean()),
        "gini_total_sent": gini(totals),
        "top10pct_share_of_sent": float(totals.nlargest(len(totals) // 10).sum() / totals.sum()),
        "median_weekly_sent_active": float(f.loc[f.sent > 0, "sent"].median()),
        "p95_weekly_sent_active": float(f.loc[f.sent > 0, "sent"].quantile(0.95)),
        "after_hours_share_overall": float(((ev.hour_est < 7) | (ev.hour_est >= 20)).mean()),
        "weekend_share_overall": float((ev.weekday_est >= 5).mean()),
        "median_reply_latency_h": float(f.reply_latency_h.median()),
    }

    # detectors on real data, no injection
    elig = f[f["sent_base"].notna()].copy()
    s = detector_scores(elig)
    top = {c: set(s[c].nlargest(int(0.02 * len(s))).index) for c in s.columns}
    jac = lambda a, b: len(a & b) / len(a | b)  # noqa: E731
    flagged = elig.loc[list(top["robust_z"]), ["person", "week"]]
    nxt = set(zip(flagged.person, flagged.week + 1))
    all_flag = set(zip(elig.loc[list(top["robust_z"]), "person"], elig.loc[list(top["robust_z"]), "week"]))
    metrics["real_data_flags_top2pct"] = {
        "jaccard_robust_z_vs_iforest_within": jac(top["robust_z"], top["iforest_within"]),
        "jaccard_robust_z_vs_iforest_cross": jac(top["robust_z"], top["iforest_cross_sectional"]),
        "jaccard_within_vs_cross_iforest": jac(top["iforest_within"], top["iforest_cross_sectional"]),
        "flag_persists_next_week": len(nxt & all_flag) / len(nxt),
        "share_of_people_flagged_at_least_once": elig.loc[list(top["robust_z"]), "person"].nunique() / elig.person.nunique(),
    }

    inj = injection_study(f)
    save_table(inj.groupby(["kind", "size", "detector"])[["roc_auc", "pr_auc", "precision_at_k"]].mean().round(4), EXP, "injection_results")
    metrics["injection"] = (
        inj.groupby(["kind", "size", "detector"])[["roc_auc", "pr_auc", "precision_at_k"]].mean().round(4).reset_index().to_dict("records")
    )
    fig_injection(inj)

    # team-level view: only aggregates over >= 5 active people leave this layer
    units = infer_units(ev)
    f["unit"] = f.person.map(units)
    act = f[(f.sent > 0) & (f.unit >= 0)]
    agg = k_anonymous_aggregate(act, ["unit", "week"], ["after_hours_share", "weekend_share", "sent"], "person", k=MIN_GROUP)
    save_table(agg.round(4), EXP, "unit_week_indicators")
    metrics["unit_aggregation"] = {
        "inferred_units": int(act.unit.nunique()),
        "unit_weeks": len(agg),
        "unit_weeks_suppressed_k5": int(agg.suppressed.sum()),
        "share_suppressed": float(agg.suppressed.mean()),
    }
    fig_unit_heatmap(agg)

    abs_metrics, per = absenteeism_analysis()
    save_table(per, EXP, "absenteeism_periods")
    metrics["absenteeism"] = abs_metrics

    save_json(metrics, EXP)
    for k in ("descriptives", "real_data_flags_top2pct", "unit_aggregation", "absenteeism"):
        print(k, metrics[k])
    print(inj.groupby(["kind", "size", "detector"]).roc_auc.mean().unstack())


if __name__ == "__main__":
    main()

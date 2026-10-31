"""Experiment 5 - Early organizational risk signals: what can be forecast, and how far ahead?

Research questions
    RQ5a  Can a team's communication load and load spikes be forecast from its
          own history, and how quickly does skill decay with the horizon?
    RQ5b  Can the collapse of an inter-team coordination channel be predicted
          from its current structure (volume, trend, reciprocity, how many
          people carry it)?
    RQ5c  Survival: do coordination channels carried by a single person
          collapse sooner than channels carried by several, after adjusting
          for volume? (the "single specialist dependency" concern)

Data
    SNAP email-Eu-core-temporal, dense window (75 weeks, ~330k emails).
    Units are inferred with Louvain on the *training* weeks only (no org chart
    is joinable to this file), so they are proxies for teams.

All targets are team-level or team-pair-level. Nothing predicts an individual.
Correlation and prediction only: none of this identifies causes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from lifelines import CoxPHFitter, KaplanMeierFitter  # noqa: E402
from lifelines.statistics import multivariate_logrank_test  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import average_precision_score, mean_absolute_error, roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from hrnexus.common import NEUTRAL, SEED, SERIES, save_fig, save_json, save_table, setup_style  # noqa: E402
from hrnexus.data import load_eu_core_temporal  # noqa: E402
from hrnexus.graph import infer_units  # noqa: E402

EXP = "e5_early_risk"
TRAIN_FRAC = 0.6
HORIZONS_W = (1, 2, 4, 8)


# --------------------------------------------------------------------------
# A. unit-level load forecasting
# --------------------------------------------------------------------------
def unit_series(ev: pd.DataFrame, units: dict) -> pd.DataFrame:
    e = ev.assign(unit=ev.src.map(units)).dropna(subset=["unit"])
    e = e[e.unit >= 0]
    e["after_hours"] = (e.hour_est < 7) | (e.hour_est >= 20)
    s = e.groupby(["unit", "week"]).agg(load=("t", "size"), after_hours=("after_hours", "mean"), senders=("src", "nunique"))
    idx = pd.MultiIndex.from_product([s.index.levels[0], range(ev.week.max() + 1)], names=["unit", "week"])
    s = s.reindex(idx).fillna({"load": 0, "senders": 0}).reset_index()
    s["after_hours"] = s.groupby("unit").after_hours.ffill().fillna(0)
    s["org_load"] = s.groupby("week").load.transform("sum")
    return s


def load_features(s: pd.DataFrame) -> pd.DataFrame:
    s = s.copy()
    s["y"] = np.log1p(s.load)
    g = s.groupby("unit")
    for lag in range(8):
        s[f"lag{lag}"] = g.y.shift(lag)
    s["mean4"] = g.y.transform(lambda x: x.rolling(4).mean())
    s["med8"] = g.load.transform(lambda x: x.rolling(8).median())
    s["slope4"] = s.lag0 - s.lag3
    s["ah0"] = s.after_hours
    s["org_lag0"] = np.log1p(s.org_load)
    s["ratio_to_med8"] = s.load / (s.med8 + 1)
    return s


FEATS = [f"lag{i}" for i in range(8)] + ["mean4", "slope4", "ah0", "org_lag0", "ratio_to_med8"]


def forecast_study(s: pd.DataFrame, split_week: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, spike_rows = [], []
    f = load_features(s)
    g = f.groupby("unit")
    for h in HORIZONS_W:
        f["target"] = g.y.shift(-h)
        # spike: load at t+h at least 1.5x the trailing 8-week median known at t
        f["spike"] = (g.load.shift(-h) >= 1.5 * (f.med8 + 1)).astype(int)
        d = f.dropna(subset=FEATS + ["target"])
        tr, te = d[d.week + h < split_week], d[d.week >= split_week]
        preds = {
            "persistence (last week)": te.lag0,
            "4-week mean": te.mean4,
            "ridge on lags": make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(tr[FEATS], tr.target).predict(te[FEATS]),
            "gradient boosting": HistGradientBoostingRegressor(max_depth=3, max_iter=300, learning_rate=0.05, random_state=SEED)
            .fit(tr[FEATS], tr.target).predict(te[FEATS]),
        }
        base = mean_absolute_error(te.target, preds["persistence (last week)"])
        for name, p in preds.items():
            mae = mean_absolute_error(te.target, p)
            rows.append({"horizon_weeks": h, "model": name, "mae_log": mae, "skill_vs_persistence": 1 - mae / base, "n_test": len(te)})
        if te.spike.nunique() == 2 and tr.spike.nunique() == 2:
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05, random_state=SEED).fit(tr[FEATS], tr.spike)
            p = clf.predict_proba(te[FEATS])[:, 1]
            spike_rows += [
                {"horizon_weeks": h, "model": "gradient boosting", "auc": roc_auc_score(te.spike, p),
                 "pr_auc": average_precision_score(te.spike, p), "base_rate": te.spike.mean()},
                {"horizon_weeks": h, "model": "current ratio to 8-week median", "auc": roc_auc_score(te.spike, te.ratio_to_med8),
                 "pr_auc": average_precision_score(te.spike, te.ratio_to_med8), "base_rate": te.spike.mean()},
            ]
    return pd.DataFrame(rows), pd.DataFrame(spike_rows)


# --------------------------------------------------------------------------
# B/C. inter-unit coordination channels
# --------------------------------------------------------------------------
def tie_panel(ev: pd.DataFrame, units: dict, window_weeks: int = 4) -> pd.DataFrame:
    e = ev.assign(us=ev.src.map(units), ud=ev.dst.map(units)).dropna(subset=["us", "ud"])
    e = e[(e.us >= 0) & (e.ud >= 0) & (e.us != e.ud)].copy()
    e["win"] = e.week // window_weeks
    n_win = (ev.week.max() + 1) // window_weeks
    e = e[e.win < n_win]
    e["a"] = e[["us", "ud"]].min(axis=1).astype(int)
    e["b"] = e[["us", "ud"]].max(axis=1).astype(int)
    e["dir_ab"] = e.us == e.a
    org = ev.assign(win=ev.week // window_weeks).groupby("win").size()
    by_sender = e.groupby(["a", "b", "win", "src"]).size().rename("n").reset_index()
    top = by_sender.groupby(["a", "b", "win"]).n.agg(["max", "sum"])
    p = e.groupby(["a", "b", "win"]).agg(
        volume=("t", "size"), ab=("dir_ab", "sum"), bridges=("src", "nunique")
    )
    p["top_bridge_share"] = top["max"] / top["sum"]
    p["reciprocity"] = np.minimum(p.ab, p.volume - p.ab) / np.maximum(p.ab, p.volume - p.ab)
    idx = pd.MultiIndex.from_tuples(
        [(a, b, w) for a, b in p.index.droplevel(2).unique() for w in range(n_win)], names=["a", "b", "win"]
    )
    p = p.reindex(idx).fillna({"volume": 0, "ab": 0, "bridges": 0}).reset_index()
    p["org_volume"] = p.win.map(org)
    p["share"] = p.volume / p.org_volume
    size = pd.Series(units).value_counts()
    p["log_size"] = np.log(p.a.map(size) * p.b.map(size))  # bigger units have more potential bridges
    return p


def tie_features(p: pd.DataFrame, min_volume: int = 10) -> pd.DataFrame:
    p = p.sort_values(["a", "b", "win"]).copy()
    g = p.groupby(["a", "b"])
    p["log_volume"] = np.log1p(p.volume)
    p["trend"] = p.log_volume - g.log_volume.shift(1)
    p["active"] = p.volume >= min_volume
    p["age"] = g.active.transform(lambda s: s.groupby((~s).cumsum()).cumcount())
    # 2-window smoothing so a single quiet month (holidays) is not read as a collapse
    p["share_s"] = g.share.transform(lambda x: x.rolling(2, min_periods=1).mean())
    p["single_bridge"] = (p.bridges == 1).astype(int)
    p["log_bridges"] = np.log1p(p.bridges)
    return p


TIE_FEATS = ["log_volume", "trend", "log_bridges", "single_bridge", "top_bridge_share", "reciprocity", "age", "log_size"]


def collapse_study(p: pd.DataFrame, split_win: int) -> pd.DataFrame:
    rows = []
    g = p.groupby(["a", "b"])
    for h in (1, 2, 3):
        d = p.copy()
        d["future_share"] = (g.share.shift(-h) + g.share.shift(-h - 1)) / 2
        d["collapse"] = (d.future_share < 0.25 * d.share_s).astype(int)
        d = d[d.active & d.future_share.notna()].dropna(subset=TIE_FEATS)
        tr, te = d[d.win + h < split_win], d[d.win >= split_win]
        for name, cols in (("volume only", ["log_volume"]), ("volume + trend", ["log_volume", "trend"]), ("full structure", TIE_FEATS)):
            lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(tr[cols], tr.collapse)
            prob = lr.predict_proba(te[cols])[:, 1]
            rows.append({"horizon_months": h, "features": name, "learner": "logistic", "auc": roc_auc_score(te.collapse, prob),
                         "pr_auc": average_precision_score(te.collapse, prob), "base_rate": te.collapse.mean(), "n_test": len(te)})
        gb = HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05, random_state=SEED).fit(tr[TIE_FEATS], tr.collapse)
        prob = gb.predict_proba(te[TIE_FEATS])[:, 1]
        rows.append({"horizon_months": h, "features": "full structure", "learner": "gradient boosting", "auc": roc_auc_score(te.collapse, prob),
                     "pr_auc": average_precision_score(te.collapse, prob), "base_rate": te.collapse.mean(), "n_test": len(te)})
    return pd.DataFrame(rows)


def survival_study(p: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Spell = a channel from the first window it is active (after window 0, so a
    smoothed reference exists) until its 2-window mean share of organisation-wide
    email falls below 25% of its smoothed share at entry (event), or the data end
    (censored). Covariates are measured at entry."""
    recs = []
    last = p.win.max()
    for (a, b), t in p.groupby(["a", "b"]):
        t = t.sort_values("win").reset_index(drop=True)
        act = t[t.active & (t.win >= 1) & (t.win < last - 1)]
        if act.empty:
            continue
        e = act.iloc[0]
        fut = (t.share + t.share.shift(-1)) / 2
        later = t[(t.win > e.win) & (t.win < last)]
        dead = later[fut.loc[later.index] < 0.25 * e.share_s]
        recs.append({
            "duration": (dead.win.iloc[0] - e.win) if len(dead) else (last - 1 - e.win),
            "event": int(len(dead) > 0),
            "log_volume": e.log_volume,
            "reciprocity": 0.0 if np.isnan(e.reciprocity) else e.reciprocity,
            "log_bridges": np.log(e.bridges),
            "bridges": e.bridges,
            "bridges_cat": "1-2 people" if e.bridges <= 2 else ("3-5 people" if e.bridges <= 5 else "6+ people"),
            "top_bridge_share": e.top_bridge_share,
            "log_size": e.log_size,
        })
    s = pd.DataFrame(recs)
    cph = CoxPHFitter(penalizer=0.01)
    cph.fit(s[["duration", "event", "log_volume", "reciprocity", "log_bridges", "top_bridge_share", "log_size"]], "duration", "event")
    summ = cph.summary[["exp(coef)", "exp(coef) lower 95%", "exp(coef) upper 95%", "p"]]
    lr = multivariate_logrank_test(s.duration, s.bridges_cat, s.event)
    out = {
        "channels": len(s),
        "events": int(s.event.sum()),
        "by_bridges": s.groupby("bridges_cat").agg(n=("event", "size"), event_rate=("event", "mean"), median_log_volume=("log_volume", "median")).round(3).to_dict("index"),
        "cox_hazard_ratios": summ.round(4).to_dict("index"),
        "cox_concordance": cph.concordance_index_,
        "logrank_p": lr.p_value,
        "ph_assumption_note": "check with cph.check_assumptions; reported as indicative",
    }
    return out, s


# --------------------------------------------------------------------------
def fig_forecast(fc: pd.DataFrame, sp: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9))
    for i, m in enumerate(["4-week mean", "ridge on lags", "gradient boosting"]):
        d = fc[fc.model == m]
        axes[0].plot(d.horizon_weeks, d.skill_vs_persistence, marker="o", ms=5, color=SERIES[i], label=m)
    axes[0].axhline(0, color=NEUTRAL, lw=1)
    axes[0].set_xlabel("forecast horizon (weeks)")
    axes[0].set_ylabel("MAE skill vs. 'same as last week'")
    axes[0].set_title("Unit communication-load forecast", fontsize=10)
    axes[0].legend()
    for i, m in enumerate(["gradient boosting", "current ratio to 8-week median"]):
        d = sp[sp.model == m]
        axes[1].plot(d.horizon_weeks, d.auc, marker="o", ms=5, color=SERIES[i], label=m)
    axes[1].axhline(0.5, color=NEUTRAL, lw=1)
    axes[1].set_ylim(0.4, 1)
    axes[1].set_xlabel("forecast horizon (weeks)")
    axes[1].set_ylabel("ROC-AUC")
    axes[1].set_title("Load-spike (>=1.5x 8-week median) prediction", fontsize=10)
    axes[1].legend()
    fig.suptitle("How far ahead can team-level pressure be anticipated?", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save_fig(fig, EXP, "forecast_horizon")


def fig_collapse(cs: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.9))
    combos = [("volume only", "logistic"), ("volume + trend", "logistic"), ("full structure", "logistic"), ("full structure", "gradient boosting")]
    for i, (f, l) in enumerate(combos):
        d = cs[(cs.features == f) & (cs.learner == l)]
        ax.plot(d.horizon_months, d.auc, marker="o", ms=5, color=SERIES[i], label=f"{f} ({l})")
    ax.axhline(0.5, color=NEUTRAL, lw=1)
    ax.set_ylim(0.4, 1)
    ax.set_xticks([1, 2, 3])
    ax.set_xlabel("horizon (4-week windows)")
    ax.set_ylabel("ROC-AUC")
    ax.set_title("Predicting collapse of inter-unit coordination channels")
    ax.legend(fontsize=7.5)
    save_fig(fig, EXP, "channel_collapse")


def fig_km(s: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    for i, cat in enumerate(["1-2 people", "3-5 people", "6+ people"]):
        d = s[s.bridges_cat == cat]
        km = KaplanMeierFitter().fit(d.duration, d.event, label=f"carried by {cat} (n={len(d)})")
        km.plot_survival_function(ax=ax, ci_show=True, color=SERIES[i], lw=2)
    ax.set_xlabel("4-week windows since channel became active")
    ax.set_ylabel("share of channels not yet collapsed")
    ax.set_ylim(0, 1.02)
    ax.set_title("Coordination channels carried by fewer people collapse sooner")
    ax.legend(fontsize=8)
    save_fig(fig, EXP, "channel_survival")


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    ev = load_eu_core_temporal()
    n_weeks = ev.week.max() + 1
    split_week = int(TRAIN_FRAC * n_weeks)
    units = infer_units(ev[ev.week < split_week])  # no look-ahead into test weeks
    metrics: dict = {"weeks": int(n_weeks), "split_week": split_week, "inferred_units": int(len(set(units.values()) - {-1}))}

    s = unit_series(ev, units)
    fc, sp = forecast_study(s, split_week)
    save_table(fc.round(4), EXP, "load_forecast")
    save_table(sp.round(4), EXP, "spike_prediction")
    metrics["load_forecast"] = fc.round(4).to_dict("records")
    metrics["spike_prediction"] = sp.round(4).to_dict("records")
    fig_forecast(fc, sp)

    p = tie_features(tie_panel(ev, units))
    n_win = p.win.max() + 1
    split_win = int(TRAIN_FRAC * n_win)
    cs = collapse_study(p, split_win)
    save_table(cs.round(4), EXP, "channel_collapse")
    metrics["channel_collapse"] = cs.round(4).to_dict("records")
    metrics["channel_panel"] = {"unit_pairs": int(p.groupby(["a", "b"]).ngroups), "windows": int(n_win), "split_window": split_win,
                                "active_channel_windows": int(p.active.sum())}
    fig_collapse(cs)

    surv, spells = survival_study(p)
    metrics["channel_survival"] = surv
    fig_km(spells)

    save_json(metrics, EXP)
    print(fc.pivot(index="horizon_weeks", columns="model", values="skill_vs_persistence").round(3))
    print(sp.round(3))
    print(cs.round(3))
    print({k: v for k, v in surv.items() if k != "by_bridges"})
    print(surv["by_bridges"])


if __name__ == "__main__":
    main()

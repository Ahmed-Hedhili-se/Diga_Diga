"""Experiment 4 - Work conditions and self-reported well-being (and what metadata cannot see).

Research questions
    RQ4a  In a real, representative worker survey, how strongly are workload,
          job control, social support and work-family conflict associated
          with self-reported stress, exhaustion and job dissatisfaction?
    RQ4b  How much of self-reported stress can be predicted from the variables
          an HR system could observe in logs (hours worked, extra-hour days,
          email hours), compared with what employees *report* about their work?
    RQ4c  Does the Job Demands-Control-Support (Karasek/Johnson) pattern
          replicate: high demands + low control -> most strain; does support
          or control buffer demands?
    RQ4d  Are the relationships stable across survey waves (2002-2022)?

Data
    NORC General Social Survey, Quality of Worklife (QWL) module, waves 2002,
    2006, 2010, 2014, 2018, 2022 (real, US probability sample of workers,
    designed with NIOSH). Single-item measures, not CBI/COPSOQ scales.
    Plus an audit of IBM's fictional HR attrition dataset, to show why
    synthetic HR data cannot answer these questions.

Everything here is cross-sectional and observational: associations, not causes.
No job-performance measure exists in the GSS; see the report for why public
data cannot test the well-being -> performance link and how to collect it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy.stats import norm, spearmanr  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.model_selection import RepeatedStratifiedKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from hrnexus.common import NEUTRAL, SEED, SERIES, TEXT2, save_fig, save_json, save_table, setup_style  # noqa: E402
from hrnexus.data import load_gss_qwl, load_ibm_hr  # noqa: E402

EXP = "e4_wellbeing"

DEMOG = ["age", "female", "self_employed"]
OBSERVABLE = ["hours_week", "extra_hour_days"]
DEMANDS = ["too_much_work", "must_work_fast", "understaffed", "conflicting_demands"]
RESOURCES = ["job_freedom", "schedule_control", "role_clarity", "treated_with_respect", "coworker_support", "supervisor_support"]
INTERFACE = ["work_family_interference"]
LABELS = {
    "hours_week": "hours worked last week (per 10 h)",
    "extra_hour_days": "days with extra hours, past month (per 10 days)",
    "email_hours": "hours per week on email (per 10 h)",
    "too_much_work": "too much work to do everything well",
    "must_work_fast": "job requires working very fast",
    "understaffed": "not enough staff (often)",
    "conflicting_demands": "conflicting demands",
    "job_freedom": "freedom to decide how to do the job",
    "schedule_control": "can change start/quit times",
    "role_clarity": "knows what is expected",
    "treated_with_respect": "treated with respect",
    "coworker_support": "co-workers can be relied on",
    "supervisor_support": "supervisor helpful",
    "work_family_interference": "job interferes with family life",
}


# --------------------------------------------------------------------------
def prepare() -> pd.DataFrame:
    raw = load_gss_qwl()
    d = raw[raw.wrkstat.isin([1, 2, 3]) & raw.stress.notna()].copy()
    rev4 = lambda s: (4 - s) / 3  # noqa: E731  1 = "strongly agree/very true/often" -> 1.0
    d["high_stress"] = d.stress.isin([1, 2]).astype(int)
    d["exhausted"] = d.usedup.isin([1, 2]).astype(float).where(d.usedup.notna())
    d["dissatisfied"] = d.satjob1.isin([3, 4]).astype(float).where(d.satjob1.notna())
    d["hours_week"] = d.hrs1.clip(upper=89) / 10
    d["extra_hour_days"] = d.moredays.clip(upper=30) / 10
    d["email_hours"] = (d.emailhr.astype(float).fillna(0) + d.emailmin.astype(float).fillna(0) / 60).where(d.emailhr.notna()).clip(upper=60) / 10
    d["too_much_work"] = rev4(d.overwork)
    d["must_work_fast"] = rev4(d.workfast)
    d["understaffed"] = rev4(d.toofewwk)
    d["conflicting_demands"] = (d.condemnd - 1) / 3
    d["job_freedom"] = rev4(d.wkfreedm)
    d["schedule_control"] = rev4(d.chngtme)
    d["role_clarity"] = rev4(d.knowwhat)
    d["treated_with_respect"] = rev4(d.respect)
    d["coworker_support"] = rev4(d.cowrkhlp)
    d["supervisor_support"] = rev4(d.suphelp)
    d["work_family_interference"] = rev4(d.wkvsfam)
    d["female"] = (d.sex == 2).astype(int)
    d["self_employed"] = (d.wrkslf == 1).astype(int)
    d["weight"] = d.weight / d.groupby("year").weight.transform("mean")
    return d


def wmean_ci(y: pd.Series, w: pd.Series) -> tuple[float, float, float]:
    m = np.average(y, weights=w)
    n_eff = w.sum() ** 2 / (w**2).sum()
    se = np.sqrt(m * (1 - m) / n_eff)
    return m, m - 1.96 * se, m + 1.96 * se


# --------------------------------------------------------------------------
def model_ladder(d: pd.DataFrame, outcome: str, ladders: dict, sample_cols: list[str]) -> pd.DataFrame:
    s = d.dropna(subset=sample_cols + [outcome])
    y = s[outcome].astype(int).values
    year_dum = pd.get_dummies(s.year, prefix="y", drop_first=True).astype(float)
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=SEED)
    rows = []
    for name, cols in ladders.items():
        x = pd.concat([s[cols], year_dum], axis=1).values
        for model_name, make in (
            ("logistic", lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000))),
            ("gradient boosting", lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, random_state=SEED)),
        ):
            aucs, briers = [], []
            for tr, te in cv.split(x, y):
                m = make().fit(x[tr], y[tr])
                p = m.predict_proba(x[te])[:, 1]
                aucs.append(roc_auc_score(y[te], p))
                briers.append(brier_score_loss(y[te], p))
            rows.append(
                {"outcome": outcome, "model_set": name, "learner": model_name, "n": len(s),
                 "prevalence": y.mean(), "auc_mean": np.mean(aucs), "auc_sd": np.std(aucs),
                 "brier": np.mean(briers), "brier_null": y.mean() * (1 - y.mean())}
            )
    return pd.DataFrame(rows)


def temporal_generalization(d: pd.DataFrame, ladders: dict, sample_cols: list[str]) -> pd.DataFrame:
    s = d.dropna(subset=sample_cols)
    rows = []
    for name, cols in ladders.items():
        tr = s[s.year <= 2014]
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)).fit(tr[cols], tr.high_stress)
        for yr in (2018, 2022):
            te = s[s.year == yr]
            rows.append({"model_set": name, "test_year": yr, "auc": roc_auc_score(te.high_stress, m.predict_proba(te[cols])[:, 1]), "n_test": len(te)})
    return pd.DataFrame(rows)


def weighted_logit(d: pd.DataFrame, outcome: str, cols: list[str], extra: list[str] | None = None) -> tuple[pd.DataFrame, object]:
    s = d.dropna(subset=cols + [outcome, "weight"]).copy()
    for a, b in extra or []:
        s[f"{a} x {b}"] = (s[a] - s[a].mean()) * (s[b] - s[b].mean())
    terms = cols + [f"{a} x {b}" for a, b in (extra or [])]
    x = pd.concat([s[terms], pd.get_dummies(s.year, prefix="y", drop_first=True).astype(float)], axis=1)
    x = sm.add_constant(x)
    res = sm.GLM(s[outcome].astype(float), x, family=sm.families.Binomial(), var_weights=s.weight).fit(cov_type="HC1")
    ci = res.conf_int()
    tab = pd.DataFrame({
        "odds_ratio": np.exp(res.params), "ci_low": np.exp(ci[0]), "ci_high": np.exp(ci[1]), "p_value": res.pvalues,
    }).loc[terms]
    return tab, res


def power_table() -> pd.DataFrame:
    rows = []
    za, zb = norm.ppf(0.975), norm.ppf(0.8)
    for r in (0.1, 0.2, 0.3, 0.5):
        n = ((za + zb) / np.arctanh(r)) ** 2 + 3
        rows.append({"true_correlation": r, "n_units_for_80pct_power": int(np.ceil(n))})
    return pd.DataFrame(rows)


def ibm_audit() -> dict:
    df = load_ibm_hr()
    sat = ["JobSatisfaction", "EnvironmentSatisfaction", "RelationshipSatisfaction", "WorkLifeBalance", "JobInvolvement"]
    c = df[sat + ["PerformanceRating"]].corr(method="spearman")
    off = c.loc[sat, sat].values[np.triu_indices(len(sat), 1)]
    perf = df.PerformanceRating.value_counts().sort_index().to_dict()
    ot = df.OverTime.eq("Yes").astype(int)
    return {
        "rows": len(df),
        "performance_rating_values": {int(k): int(v) for k, v in perf.items()},
        "max_abs_spearman_between_satisfaction_items": float(np.abs(off).max()),
        "spearman_performance_vs_satisfaction_items": {k: float(c.loc["PerformanceRating", k]) for k in sat},
        "spearman_overtime_vs_worklifebalance": float(spearmanr(ot, df.WorkLifeBalance).statistic),
        "spearman_overtime_vs_jobsatisfaction": float(spearmanr(ot, df.JobSatisfaction).statistic),
        "spearman_overtime_vs_attrition": float(spearmanr(ot, df.Attrition.eq("Yes")).statistic),
        "share_by_jobsatisfaction_level": df.JobSatisfaction.value_counts(normalize=True).sort_index().round(3).to_dict(),
    }


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def fig_ladder(lad: pd.DataFrame) -> None:
    order = ["demographics", "+ observable hours", "+ reported demands", "+ resources & work-family"]
    outs = [("high_stress", "often/always stressed"), ("exhausted", "often 'used up'"), ("dissatisfied", "dissatisfied with job")]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(order))
    for i, (o, lab) in enumerate(outs):
        s = lad[(lad.outcome == o) & (lad.learner == "logistic")].set_index("model_set").loc[order]
        ax.errorbar(x + (i - 1) * 0.08, s.auc_mean, yerr=s.auc_sd, marker="o", ms=5, capsize=3, color=SERIES[i], label=lab)
    ax.axhline(0.5, color=NEUTRAL, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(order, fontsize=8)
    ax.set_ylim(0.45, 0.9)
    ax.set_ylabel("cross-validated ROC-AUC")
    ax.set_title("What predicts self-reported strain? GSS Quality of Worklife 2002-2022")
    ax.legend(loc="upper left")
    save_fig(fig, EXP, "prediction_ladder")


def fig_forest(tab: pd.DataFrame, name: str, title: str) -> None:
    t = tab.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.36 * len(t) + 1.2))
    y = np.arange(len(t))
    colors = [SERIES[1] if lo > 1 else SERIES[0] if hi < 1 else NEUTRAL for lo, hi in zip(t.ci_low, t.ci_high)]
    ax.hlines(y, t.ci_low, t.ci_high, color=colors, lw=2)
    ax.scatter(t.odds_ratio, y, color=colors, s=36, zorder=3, edgecolors="#fcfcfb", linewidths=1.5)
    ax.axvline(1, color=NEUTRAL, lw=1)
    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels([LABELS.get(i, i) for i in t.index], fontsize=8)
    ax.set_xlabel("odds ratio for 'often/always stressed' (full scale change; 95% CI, survey-weighted, robust SE)")
    ax.set_title(title)
    ax.scatter([], [], color=SERIES[1], label="higher odds")
    ax.scatter([], [], color=SERIES[0], label="lower odds")
    ax.scatter([], [], color=NEUTRAL, label="CI includes 1")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    save_fig(fig, EXP, name)


def fig_dose(d: pd.DataFrame) -> dict:
    out = {}
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
    bins = [0, 30, 40, 41, 50, 60, 200]
    labs = ["<30", "30-39", "40", "41-49", "50-59", "60+"]
    s = d.dropna(subset=["hrs1"])
    s = s.assign(hb=pd.cut(s.hrs1, bins=bins, right=False, labels=labs))
    rows = [(lab, *wmean_ci(g.high_stress, g.weight), len(g)) for lab, g in s.groupby("hb", observed=True)]
    out["by_hours"] = rows
    r = pd.DataFrame(rows, columns=["bin", "p", "lo", "hi", "n"])
    axes[0].bar(r.bin, r.p, color=SERIES[0], width=0.6)
    axes[0].errorbar(r.bin, r.p, yerr=[r.p - r.lo, r.hi - r.p], fmt="none", color=TEXT2, capsize=3)
    axes[0].set_xlabel("hours worked last week")
    axes[0].set_ylabel("share often/always stressed (weighted)")
    axes[0].set_title("Observable: hours", fontsize=10)

    s = d.dropna(subset=["overwork"])
    labs2 = {1: "strongly\nagree", 2: "agree", 3: "disagree", 4: "strongly\ndisagree"}
    rows = [(labs2[int(k)], *wmean_ci(g.high_stress, g.weight), len(g)) for k, g in s.groupby("overwork")]
    out["by_too_much_work"] = rows
    r = pd.DataFrame(rows, columns=["bin", "p", "lo", "hi", "n"])
    axes[1].bar(r.bin, r.p, color=SERIES[1], width=0.6)
    axes[1].errorbar(r.bin, r.p, yerr=[r.p - r.lo, r.hi - r.p], fmt="none", color=TEXT2, capsize=3)
    axes[1].set_xlabel("'I have too much work to do everything well'")
    axes[1].set_title("Reported: overload", fontsize=10)

    s = d.dropna(subset=["overwork", "wkfreedm"])
    s = s.assign(
        demand=np.where(s.overwork <= 2, "high demand", "low demand"),
        control=np.where(s.wkfreedm <= 1, "high control", "low control"),
    )
    order = [("low demand", "high control"), ("low demand", "low control"), ("high demand", "high control"), ("high demand", "low control")]
    names = ["low demand\nhigh control", "low demand\nlow control", "high demand\nhigh control", "high demand\nlow control"]
    rows = []
    for (dm, ct), nm in zip(order, names):
        g = s[(s.demand == dm) & (s.control == ct)]
        rows.append((nm.replace("\n", " "), *wmean_ci(g.high_stress, g.weight), len(g)))
    out["karasek_quadrants"] = rows
    r = pd.DataFrame(rows, columns=["bin", "p", "lo", "hi", "n"])
    axes[2].bar(names, r.p, color=[SERIES[0], SERIES[0], SERIES[0], SERIES[1]], width=0.6)
    axes[2].errorbar(names, r.p, yerr=[r.p - r.lo, r.hi - r.p], fmt="none", color=TEXT2, capsize=3)
    axes[2].tick_params(axis="x", labelsize=7)
    axes[2].set_title("Demand-control quadrants", fontsize=10)
    for ax in axes:
        ax.grid(axis="x", visible=False)
    fig.suptitle("Share reporting work is often/always stressful (GSS QWL 2002-2022, 95% CI)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save_fig(fig, EXP, "stress_gradients")
    return out


def fig_trend(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for yr, g in d.groupby("year"):
        for o in ("high_stress", "exhausted"):
            gg = g.dropna(subset=[o])
            m, lo, hi = wmean_ci(gg[o], gg.weight)
            rows.append({"year": yr, "outcome": o, "p": m, "lo": lo, "hi": hi, "n": len(gg)})
    t = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(6, 3.8))
    for i, (o, lab) in enumerate((("high_stress", "work often/always stressful"), ("exhausted", "often/very often 'used up'"))):
        s = t[t.outcome == o]
        ax.plot(s.year, s.p, marker="o", ms=5, color=SERIES[i], label=lab)
        ax.fill_between(s.year, s.lo, s.hi, color=SERIES[i], alpha=0.15, lw=0)
    ax.set_ylim(0, 0.5)
    ax.set_ylabel("weighted share of workers")
    ax.set_title("Strain over time, US workers (GSS QWL)")
    ax.legend(loc="upper left")
    save_fig(fig, EXP, "strain_trend")
    return t


def fig_shap(d: pd.DataFrame, cols: list[str]) -> dict:
    s = d.dropna(subset=cols + ["high_stress"])
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, random_state=SEED).fit(s[cols], s.high_stress)
    try:
        import shap

        sv = shap.TreeExplainer(m).shap_values(s[cols])
        imp = pd.Series(np.abs(sv).mean(0), index=cols)
        method = "mean |SHAP| (log-odds)"
    except Exception:  # pragma: no cover - shap optional
        from sklearn.inspection import permutation_importance

        r = permutation_importance(m, s[cols], s.high_stress, scoring="roc_auc", n_repeats=5, random_state=SEED)
        imp = pd.Series(r.importances_mean, index=cols)
        method = "permutation importance (AUC drop)"
    imp = imp.sort_values()
    fig, ax = plt.subplots(figsize=(6.8, 5))
    colors = [SERIES[1] if c in OBSERVABLE else SERIES[0] for c in imp.index]
    ax.barh([LABELS.get(c, c) for c in imp.index], imp.values, color=colors, height=0.65)
    ax.barh([], [], color=SERIES[1], label="observable from time/IT systems")
    ax.barh([], [], color=SERIES[0], label="only known if employees report it")
    ax.legend(loc="lower right")
    ax.set_xlabel(method)
    ax.set_title("What a gradient-boosting model relies on (stress)")
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", visible=False)
    save_fig(fig, EXP, "importance_stress")
    return {"method": method, "importance": imp.round(4).to_dict()}


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    d = prepare()
    metrics: dict = {
        "sample": {
            "respondents_working_with_stress_item": len(d),
            "by_year": d.year.value_counts().sort_index().to_dict(),
            "weighted_prevalence_high_stress": float(np.average(d.high_stress, weights=d.weight)),
        }
    }
    metrics["trend"] = fig_trend(d).round(4).to_dict("records")

    ladders = {
        "demographics": DEMOG,
        "+ observable hours": DEMOG + OBSERVABLE,
        "+ reported demands": DEMOG + OBSERVABLE + DEMANDS,
        "+ resources & work-family": DEMOG + OBSERVABLE + DEMANDS + RESOURCES + INTERFACE,
    }
    full_cols = DEMOG + OBSERVABLE + DEMANDS + RESOURCES + INTERFACE
    lad = pd.concat([model_ladder(d, o, ladders, full_cols) for o in ("high_stress", "exhausted", "dissatisfied")])
    save_table(lad.round(4), EXP, "prediction_ladder")
    metrics["prediction_ladder"] = lad.round(4).to_dict("records")
    fig_ladder(lad)

    # digital-trace proxy: add email hours (not asked in 2006)
    email_ladders = {
        "demographics": DEMOG,
        "+ hours + email hours": DEMOG + OBSERVABLE + ["email_hours"],
        "+ everything reported": full_cols + ["email_hours"],
    }
    lad_e = model_ladder(d[d.year != 2006], "high_stress", email_ladders, full_cols + ["email_hours"])
    save_table(lad_e.round(4), EXP, "prediction_ladder_email")
    metrics["prediction_ladder_email"] = lad_e.round(4).to_dict("records")

    tg = temporal_generalization(d, {k: ladders[k] for k in ("+ observable hours", "+ resources & work-family")}, full_cols + ["high_stress"])
    metrics["temporal_generalization"] = tg.round(4).to_dict("records")

    main_terms = OBSERVABLE + DEMANDS + RESOURCES + INTERFACE
    tab, res = weighted_logit(d, "high_stress", DEMOG + main_terms)
    save_table(tab.round(4), EXP, "weighted_logit_high_stress")
    metrics["weighted_logit_high_stress"] = tab.loc[main_terms].round(4).to_dict("index")
    metrics["weighted_logit_n"] = int(res.nobs)
    fig_forest(tab.loc[main_terms], "odds_ratios_stress", "Adjusted associations with frequent work stress")

    tab_ex, _ = weighted_logit(d, "exhausted", DEMOG + main_terms)
    save_table(tab_ex.round(4), EXP, "weighted_logit_exhausted")
    metrics["weighted_logit_exhausted"] = tab_ex.loc[main_terms].round(4).to_dict("index")

    inter, _ = weighted_logit(
        d, "high_stress", DEMOG + main_terms,
        extra=[("too_much_work", "job_freedom"), ("too_much_work", "coworker_support"), ("too_much_work", "supervisor_support")],
    )
    metrics["jdcs_interactions"] = inter.filter(like=" x ", axis=0).round(4).to_dict("index")

    metrics["gradients"] = fig_dose(d)
    metrics["gbm_importance"] = fig_shap(d, OBSERVABLE + DEMANDS + RESOURCES + INTERFACE + ["age", "female"])

    s = d.dropna(subset=["hrs1", "high_stress"])
    metrics["observable_correlations"] = {
        "spearman_hours_vs_stress_item": float(spearmanr(s.hrs1, -s.stress).statistic),
        "spearman_too_much_work_vs_stress_item": float(spearmanr(d.dropna(subset=["overwork"]).too_much_work, -d.dropna(subset=["overwork"]).stress).statistic),
        "spearman_work_family_vs_stress_item": float(spearmanr(d.dropna(subset=["wkvsfam"]).work_family_interference, -d.dropna(subset=["wkvsfam"]).stress).statistic),
    }
    pt = power_table()
    save_table(pt, EXP, "power_table")
    metrics["power_table"] = pt.to_dict("records")
    metrics["ibm_fictional_audit"] = ibm_audit()

    save_json(metrics, EXP)
    print(lad[lad.learner == "logistic"][["outcome", "model_set", "n", "prevalence", "auc_mean"]])
    print(lad_e[lad_e.learner == "logistic"][["model_set", "n", "auc_mean"]])
    print(tg)
    print(tab.round(3))
    print(metrics["jdcs_interactions"])
    print(metrics["ibm_fictional_audit"])
    print(metrics["observable_correlations"])


if __name__ == "__main__":
    main()

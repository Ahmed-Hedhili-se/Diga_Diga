"""Experiment 6 - Multi-objective what-if simulation for HR decision support.

SYNTHETIC DEMONSTRATION. No real organization is modelled and no result here
is an empirical finding about people. The point is to show *how* a decision-
support layer should present trade-offs, and how much the ranking of options
depends on assumptions that nobody has measured.

Model (weekly, 26 weeks, Monte Carlo with common random numbers)
    * 24 people in 4 teams of 6, contracted 40 h, 12 h/week of meetings.
    * Each team receives gamma-distributed work at ~97% of its focus capacity,
      with a +30% surge in weeks 8-15.
    * 25% of completed work needs a review that only one specialist (team 0)
      is qualified for -> a deliberate single-specialist bottleneck.
    * Cross-team handoffs cause rework; documentation reduces it.
    * Overtime is used when backlog exceeds capacity, up to a policy cap.
    * Absence: 2%/week baseline. ASSUMPTION under test: absence risk rises with
      a person's trailing 4-week average hours above 45 h (beta). beta=0 means
      no such feedback. The real size of this effect is unknown; E4 shows long
      hours are *associated* with reported strain, which is not the same thing.

Decision levers: allocation (concentrated vs balanced), overtime cap, hires,
cross-training reviewers, documentation, meeting reduction.

Objectives reported (never collapsed into one score):
    output delivered, share of person-weeks over 48 h (EU Working Time Directive
    average limit), peak individual average hours, share of reviews done by one
    person (key-person dependency), output lost if the specialist is absent for
    four weeks (resilience), added headcount.
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from hrnexus.common import MUTED, NEUTRAL, SEED, SERIES, TEXT2, save_fig, save_json, save_table, setup_style  # noqa: E402

EXP = "e6_scenarios"
T, TEAMS, PER = 26, 4, 6
CONTRACT, MEETINGS = 40.0, 12.0
REVIEW_FRAC, REVIEW_EFFORT = 0.25, 0.25
HANDOFF, REWORK = 0.30, 0.50
SURGE = range(8, 16)
SHOCK_WEEKS = range(12, 16)
TRAINEES = (6, 12)  # first member of teams 1 and 2
REPS = 60
ASSUMPTIONS = [(0.0, 0.0), (0.03, 0.0), (0.06, 0.0), (0.03, 0.4)]  # (absence feedback beta, meeting-cut handoff penalty)


@dataclass(frozen=True)
class Policy:
    allocation: str = "concentrated"  # or "balanced"
    overtime_cap: float = 10.0
    hires: int = 0
    cross_train: int = 0
    documentation: bool = False
    meeting_cut: float = 0.0


def simulate(pol: Policy, beta: float, shock: bool, reps: int = REPS, seed: int = SEED, meeting_penalty: float = 0.0) -> dict:
    rng = np.random.default_rng(seed)  # same seed across policies: common random numbers
    n0 = TEAMS * PER
    n = n0 + pol.hires
    team = np.concatenate([np.repeat(np.arange(TEAMS), PER), np.arange(pol.hires) % TEAMS])
    prod = rng.uniform(0.8, 1.2, (reps, n))
    meetings = MEETINGS * (1 - pol.meeting_cut)
    mu = 0.97 * PER * (CONTRACT - MEETINGS)  # demand set against the *baseline* focus capacity
    arrivals = rng.gamma(16, mu / 16, (reps, T, TEAMS))
    arrivals[:, list(SURGE), :] *= 1.3
    abs_draw = rng.random((reps, T, n))

    backlog = np.full((reps, TEAMS), 0.5 * mu)
    pending = np.zeros(reps)  # work hours awaiting review
    delivered = np.zeros(reps)
    hours = np.zeros((reps, T, n))
    present_hist = np.zeros((reps, T, n), dtype=bool)
    review_hours = np.zeros((reps, n))

    reviewer_prod = np.zeros(n)
    reviewer_prod[0] = 1.0
    trainees = list(TRAINEES[: pol.cross_train])

    for t in range(T):
        # ---- who is at work -------------------------------------------------
        h4 = hours[:, max(0, t - 4):t, :].mean(axis=1) if t else np.full((reps, n), CONTRACT)
        p_abs = 0.02 + beta * np.maximum(0, h4 - 45) / 10
        present = abs_draw[:, t, :] >= p_abs
        present[:, n0:] &= t >= 4  # hires start in week 4
        if shock and t in SHOCK_WEEKS:
            present[:, 0] = False

        eff = prod.copy()
        if pol.hires:
            eff[:, n0:] *= min(1.0, 0.3 + 0.7 * max(0, t - 4) / 8)

        overhead = np.zeros(n)
        for i in trainees:
            if t < 6:
                overhead[i] += 4.0
        for j in range(pol.hires):  # a team-mate mentors each new hire
            if 4 <= t < 12:
                overhead[PER * (j % TEAMS) + 1] += 4.0
        if pol.documentation and t < 4:
            overhead += 10.0 / PER
        focus = np.clip(CONTRACT - meetings - overhead, 0, None) * present
        ot_cap = pol.overtime_cap * present

        # ---- reviews first (they gate delivery) -----------------------------
        rp = reviewer_prod.copy()
        for i in trainees:
            if t >= 6:
                rp[i] = 0.7
        cap_rev_h = (focus + ot_cap) * (rp > 0)
        need = REVIEW_EFFORT * pending  # review effort hours needed
        h_rev = np.zeros((reps, n))
        rv = np.flatnonzero(rp > 0)
        if pol.allocation == "concentrated":
            left = need.copy()
            for i in rv:  # specialist first, then trainees
                rate = rp[i] * eff[:, i]
                h = np.minimum(left / np.maximum(rate, 1e-9), cap_rev_h[:, i])
                h_rev[:, i] = h
                left -= h * rate
        else:
            left = need.copy()
            for _ in range(3):  # equal effort split among reviewers with spare capacity
                spare = cap_rev_h[:, rv] - h_rev[:, rv]
                active = spare > 1e-9
                k = np.maximum(active.sum(1), 1)
                rate = rp[rv] * eff[:, rv]
                share = (left / k)[:, None] * active
                h = np.minimum(share / np.maximum(rate, 1e-9), spare)
                h_rev[:, rv] += h
                left -= (h * rate).sum(1)
        done_eff = (h_rev * rp * eff).sum(1)
        pending -= done_eff / REVIEW_EFFORT
        delivered += done_eff / REVIEW_EFFORT
        review_hours += h_rev

        rev_focus = np.minimum(h_rev, focus)
        rem_focus = focus - rev_focus
        rem_ot = ot_cap - (h_rev - rev_focus)

        # ---- team work -------------------------------------------------------
        demand = backlog + arrivals[:, t, :]
        ot_used = h_rev - rev_focus
        completed = np.zeros((reps, TEAMS))
        for k in range(TEAMS):
            m = team == k
            reg = (rem_focus[:, m] * eff[:, m]).sum(1)
            short = np.maximum(demand[:, k] - reg, 0)
            e_m, o_m = eff[:, m], rem_ot[:, m]
            if pol.allocation == "concentrated":
                order = np.argsort(-e_m, axis=1)  # most productive take overtime first
                e_s = np.take_along_axis(e_m, order, 1)
                o_s = np.take_along_axis(o_m, order, 1)
                cap_e = np.cumsum(e_s * o_s, axis=1)
                prev = np.concatenate([np.zeros((reps, 1)), cap_e[:, :-1]], axis=1)
                use_e = np.clip(short[:, None] - prev, 0, e_s * o_s)
                h_s = use_e / np.maximum(e_s, 1e-9)
                h = np.zeros_like(h_s)
                np.put_along_axis(h, order, h_s, 1)
            else:
                per_h = short / np.maximum((e_m * (o_m > 0)).sum(1), 1e-9)
                h = np.minimum(per_h[:, None], o_m)
            ot_used[:, m] += h
            completed[:, k] = np.minimum(demand[:, k], reg + (h * e_m).sum(1))
        q = 0.15 if (pol.documentation and t >= 4) else 0.30
        q += meeting_penalty * pol.meeting_cut  # pessimistic case: fewer meetings -> worse handoffs
        rework = completed * HANDOFF * q * REWORK  # done, but must be redone: not value
        backlog = demand - completed + rework
        good = completed - rework
        delivered += ((1 - REVIEW_FRAC) * good).sum(1)
        pending += (REVIEW_FRAC * good).sum(1)

        hours[:, t, :] = (CONTRACT + ot_used) * present
        present_hist[:, t, :] = present

    pw = present_hist
    long_share = ((hours > 48) & pw).sum((1, 2)) / pw.sum((1, 2))
    avg_hours = hours.sum(1) / np.maximum(pw.sum(1), 1)
    rev_total = review_hours.sum(1)
    return {
        "output": delivered,
        "long_hours_share": long_share,
        "peak_avg_hours": avg_hours.max(1),
        "review_concentration": review_hours.max(1) / np.maximum(rev_total, 1e-9),
        "end_backlog": backlog.sum(1) + pending,
        "absence_rate": 1 - pw[:, :, :n0].mean((1, 2)),
    }


def evaluate(pol: Policy, beta: float, meeting_penalty: float = 0.0) -> dict:
    base = simulate(pol, beta, shock=False, meeting_penalty=meeting_penalty)
    hit = simulate(pol, beta, shock=True, meeting_penalty=meeting_penalty)
    loss = 1 - hit["output"] / base["output"]
    row = {**asdict(pol), "beta": beta, "meeting_penalty": meeting_penalty}
    for k, v in base.items():
        row[k] = v.mean()
        row[f"{k}_sd"] = v.std()
    row["resilience_loss"] = loss.mean()
    return row


def pareto_mask(df: pd.DataFrame, maximize: list[str], minimize: list[str]) -> np.ndarray:
    v = np.column_stack([-df[c].values for c in maximize] + [df[c].values for c in minimize])
    keep = np.ones(len(v), dtype=bool)
    for i in range(len(v)):
        if keep[i]:
            dominated = np.all(v[i] <= v, axis=1) & np.any(v[i] < v, axis=1)
            keep[dominated] = False
    return keep


NAMED = {
    "A. push output (status quo, 15 h overtime cap)": Policy("concentrated", 15, 0, 0, False, 0.0),
    "B. status quo (10 h cap)": Policy("concentrated", 10, 0, 0, False, 0.0),
    "C. balance load, 5 h cap": Policy("balanced", 5, 0, 0, False, 0.0),
    "D. C + cross-train 2 reviewers": Policy("balanced", 5, 0, 2, False, 0.0),
    "E. D + documentation + 25% fewer meetings": Policy("balanced", 5, 0, 2, True, 0.25),
    "F. E + 1 hire": Policy("balanced", 5, 1, 2, True, 0.25),
}


def explain(a: pd.Series, b: pd.Series, na: str, nb: str) -> str:
    """Deterministic, template-based trade-off statement (no LLM needed)."""
    d_out = 100 * (b.output / a.output - 1)
    return (
        f"{nb} vs {na}: output {d_out:+.1f}%; person-weeks over 48 h "
        f"{100 * a.long_hours_share:.1f}% -> {100 * b.long_hours_share:.1f}%; "
        f"peak individual average {a.peak_avg_hours:.1f} h -> {b.peak_avg_hours:.1f} h; "
        f"reviews done by one person {100 * a.review_concentration:.0f}% -> {100 * b.review_concentration:.0f}%; "
        f"output lost if the specialist is away 4 weeks {100 * a.resilience_loss:.1f}% -> {100 * b.resilience_loss:.1f}%; "
        f"added headcount {int(a.hires)} -> {int(b.hires)}."
    )


# --------------------------------------------------------------------------
def fig_pareto(df: pd.DataFrame, named: pd.DataFrame) -> None:
    d = df[df.beta == 0.03]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.scatter(100 * d.long_hours_share, d.output / 1000, s=14, color=MUTED, label="all 288 policy combinations", zorder=1)
    p = d[d.pareto]
    ax.scatter(100 * p.long_hours_share, p.output / 1000, s=24, color=SERIES[0], edgecolors="#fcfcfb", linewidths=1.2,
               label="Pareto-efficient (output, long hours, dependency, headcount)", zorder=2)
    nm = named[(named.beta == 0.03) & (named.meeting_penalty == 0)]
    for i, (name, r) in enumerate(nm.iterrows()):
        ax.scatter(100 * r.long_hours_share, r.output / 1000, s=70, color=SERIES[1], edgecolors="#fcfcfb", linewidths=2, zorder=3)
        dy = {"E": -12, "F": 6}.get(name.split(".")[0], 4)  # E and F sit almost on top of each other
        ax.annotate(name.split(".")[0], (100 * r.long_hours_share, r.output / 1000), xytext=(6, dy), textcoords="offset points",
                    fontsize=9, fontweight="bold", color="#0b0b0b")
    ax.scatter([], [], s=70, color=SERIES[1], label="named options A-F (see table)")
    ax.set_xlabel("% of person-weeks over 48 h")
    ax.set_ylabel("output delivered over 26 weeks (thousand work-hours)")
    ax.set_title("Output vs. long-hours exposure (synthetic organization, absence-feedback assumption beta=0.03)")
    ax.legend(loc="lower right", fontsize=8)
    save_fig(fig, EXP, "pareto_output_vs_long_hours")


def fig_named(named: pd.DataFrame) -> None:
    nm = named[(named.beta == 0.03) & (named.meeting_penalty == 0)]
    cols = [("output", "output (k work-hours)", 1e-3), ("long_hours_share", "% person-weeks > 48 h", 100),
            ("review_concentration", "% reviews by one person", 100), ("resilience_loss", "% output lost, specialist away 4 wks", 100)]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6), sharey=True)
    labels = [n.split(".")[0] for n in nm.index]
    for ax, (c, title, scale) in zip(axes, cols):
        v = nm[c] * scale
        ax.barh(labels, v, color=SERIES[0], height=0.6)
        if f"{c}_sd" in nm:
            ax.errorbar(v, labels, xerr=nm[f"{c}_sd"] * scale, fmt="none", color=TEXT2, capsize=2, lw=1)
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", visible=False)
    axes[0].invert_yaxis()
    fig.suptitle("Named options compared on four objectives (mean +/- SD over 60 runs; no single score)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save_fig(fig, EXP, "named_options")


def fig_sensitivity(named: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4))
    labels = [n.split(".")[0] for n in NAMED]
    names = {
        (0.0, 0.0): "no absence feedback, meetings cut freely",
        (0.03, 0.0): "absence +3 pts per 10 h over 45",
        (0.06, 0.0): "absence +6 pts per 10 h over 45",
        (0.03, 0.4): "+3 pts, and fewer meetings worsen handoffs",
    }
    for i, (b, mp) in enumerate(ASSUMPTIONS):
        d = named[(named.beta == b) & (named.meeting_penalty == mp)].loc[list(NAMED)]
        ax.plot(labels, d.output / 1000, marker="o", ms=6, color=SERIES[i], label=names[(b, mp)])
    ax.set_ylabel("output (k work-hours)")
    ax.set_xlabel("option")
    ax.set_title("Does the ranking survive the unmeasured assumptions?")
    ax.legend(fontsize=7.5)
    save_fig(fig, EXP, "assumption_sensitivity")


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    grid = [
        Policy(a, c, h, x, d, m)
        for a, c, h, x, d, m in itertools.product(
            ["concentrated", "balanced"], [0.0, 5.0, 10.0, 15.0], [0, 1, 2], [0, 1, 2], [False, True], [0.0, 0.25]
        )
    ]
    rows = [evaluate(p, b) for b in (0.0, 0.03) for p in grid]
    df = pd.DataFrame(rows)
    df["pareto"] = False
    for b in (0.0, 0.03):
        m = df.beta == b
        df.loc[m, "pareto"] = pareto_mask(df[m], ["output"], ["long_hours_share", "review_concentration", "hires"])
    save_table(df.round(5), EXP, "all_scenarios")

    named = pd.DataFrame(
        [{"option": k, **evaluate(p, b, mp)} for b, mp in ASSUMPTIONS for k, p in NAMED.items()]
    ).set_index("option")
    save_table(named.round(5), EXP, "named_options")

    nb = named[(named.beta == 0.03) & (named.meeting_penalty == 0)]
    names = list(NAMED)
    explanations = [explain(nb.loc[names[1]], nb.loc[n], names[1].split(".")[0], n.split(".")[0]) for n in names if n != names[1]]
    ref = named[(named.beta == 0) & (named.meeting_penalty == 0)].loc[names].output
    rank_corr = {
        f"beta{b}_penalty{mp}": spearmanr(ref, named[(named.beta == b) & (named.meeting_penalty == mp)].loc[names].output).statistic
        for b, mp in ASSUMPTIONS[1:]
    }
    best = {
        f"beta{b}_penalty{mp}": named[(named.beta == b) & (named.meeting_penalty == mp)].output.idxmax()
        for b, mp in ASSUMPTIONS
    }
    metrics = {
        "policies_in_grid": len(grid),
        "replications": REPS,
        "pareto_count": {str(b): int(df[(df.beta == b)].pareto.sum()) for b in (0.0, 0.03)},
        "named_options": named.round(4).reset_index().to_dict("records"),
        "explanations_vs_status_quo_beta_0.03": explanations,
        "named_output_rank_correlation_vs_optimistic": rank_corr,
        "highest_output_named_option_by_assumption": best,
        "grid_output_rank_correlation_beta0_vs_0.03": spearmanr(df[df.beta == 0].output.values, df[df.beta == 0.03].output.values).statistic,
        "max_output_policy_beta0": df[df.beta == 0].sort_values("output").iloc[-1][list(asdict(Policy()))].to_dict(),
        "max_output_policy_beta0.03": df[df.beta == 0.03].sort_values("output").iloc[-1][list(asdict(Policy()))].to_dict(),
    }
    fig_pareto(df, named)
    fig_named(named)
    fig_sensitivity(named)
    save_json(metrics, EXP)
    pd.set_option("display.width", 200)
    print(named[["beta", "meeting_penalty", "output", "long_hours_share", "peak_avg_hours", "review_concentration", "resilience_loss", "absence_rate", "end_backlog"]].round(3))
    for e in explanations:
        print("-", e)
    print(metrics["pareto_count"], rank_corr, best, metrics["grid_output_rank_correlation_beta0_vs_0.03"])
    print(metrics["max_output_policy_beta0"], metrics["max_output_policy_beta0.03"])


if __name__ == "__main__":
    main()

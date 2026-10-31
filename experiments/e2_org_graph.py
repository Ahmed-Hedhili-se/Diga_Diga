"""Experiment 2 - Organizational collaboration graph analysis.

Research question
    Can communication metadata (who emailed whom, who met whom) reconstruct how
    an organization is actually structured, and can graph metrics surface silos,
    coordination bottlenecks and key-person dependency in a way that is stable
    enough to act on?

Data (all real, public)
    * SNAP email-Eu-core: 1,005 people, 25,571 directed edges, 42 departments.
    * SNAP email-Eu-core-temporal: 332k timestamped emails over 803 days
      (node ids are not joinable to departments, so used for stability only).
    * SocioPatterns InVS15: face-to-face badge contacts in a French office
      building, 2015, with departments (replication on a second modality).

Nothing here scores an individual. Person-level metrics are computed only to
derive team-level indicators and are never written out with identifiers.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.manifold import SpectralEmbedding  # noqa: E402
from sklearn.metrics import adjusted_rand_score, f1_score, normalized_mutual_info_score  # noqa: E402

from hrnexus.common import (  # noqa: E402
    MIN_GROUP, MUTED, NEUTRAL, SEED, SERIES, TEXT2, gini, save_fig, save_json, save_table, setup_style,
)
from hrnexus.data import load_eu_core_static, load_eu_core_temporal, load_sociopatterns_workplace  # noqa: E402
from hrnexus.graph import louvain, to_weighted_undirected  # noqa: E402

EXP = "e2_org_graph"
rng = np.random.default_rng(SEED)


# --------------------------------------------------------------------------
# Department-level structure
# --------------------------------------------------------------------------
def department_table(u: nx.Graph, dept: dict, min_size: int = MIN_GROUP) -> pd.DataFrame:
    """Openness, dependency concentration and partner count per department.

    internal_lift = observed share of a department's tie-ends that stay inside
    the department / share expected if ties ignored departments (degree-
    preserving configuration null). Lift >> 1 means inward-looking.
    top_bridge_share = share of the department's cross-department ties carried
    by its single most-connected member (key-person dependency).
    """
    two_m = 2 * u.number_of_edges()
    rows = []
    members = pd.Series(dept).groupby(pd.Series(dept)).groups
    for d, nodes in members.items():
        nodes = [n for n in nodes if n in u]
        if len(nodes) < min_size:
            continue
        nodes_set = set(nodes)
        internal = external = 0
        per_member_ext = []
        partners = set()
        for n in nodes:
            ext_n = 0
            for nb in u.neighbors(n):
                if nb in nodes_set:
                    internal += 1
                else:
                    external += 1
                    ext_n += 1
                    partners.add(dept.get(nb))
            per_member_ext.append(ext_n)
        ends = internal + external
        vol = sum(dict(u.degree(nodes)).values())
        expected_internal = vol / two_m if two_m else np.nan
        per_member_ext = np.sort(np.array(per_member_ext))[::-1]
        cum = np.cumsum(per_member_ext) / max(external, 1)
        rows.append(
            {
                "department": d,
                "size": len(nodes),
                "internal_density": (internal / 2) / (len(nodes) * (len(nodes) - 1) / 2),
                "ei_index": (external - internal) / ends if ends else np.nan,
                "internal_share": internal / ends if ends else np.nan,
                "internal_lift": (internal / ends) / expected_internal if ends else np.nan,
                "partner_departments": len(partners),
                "members_with_external_tie": float(np.mean(per_member_ext > 0)),
                "top_bridge_share": per_member_ext[0] / external if external else np.nan,
                "people_for_80pct_external": int(np.searchsorted(cum, 0.8) + 1) if external else 0,
            }
        )
    return pd.DataFrame(rows).set_index("department").sort_values("internal_lift", ascending=False)


def flag_departments(tab: pd.DataFrame) -> pd.DataFrame:
    """Transparent, rule-based flags (thresholds are documented, not learned)."""
    tab = tab.copy()
    tab["flag_inward"] = tab["internal_lift"] >= tab["internal_lift"].quantile(0.75)
    # strict '<' so that when every department reaches every other none is flagged
    tab["flag_low_reach"] = tab["partner_departments"] < tab["partner_departments"].quantile(0.25)
    tab["flag_single_bridge"] = tab["top_bridge_share"] >= 0.5
    tab["flag_silo_candidate"] = tab["flag_inward"] & tab["flag_low_reach"]
    return tab


# --------------------------------------------------------------------------
# Can structure reconstruct the formal organization?
# --------------------------------------------------------------------------
def community_vs_departments(u: nx.Graph, dept: dict, seeds=range(10)) -> dict:
    nodes = [n for n in u if u.degree(n) > 0 and n in dept]
    truth = [dept[n] for n in nodes]
    runs = []
    parts = []
    for s in seeds:
        p = louvain(u.subgraph(nodes), seed=SEED + s)
        lab = [p[n] for n in nodes]
        parts.append(lab)
        runs.append(
            {
                "nmi": normalized_mutual_info_score(truth, lab),
                "ari": adjusted_rand_score(truth, lab),
                "n_communities": len(set(lab)),
                "modularity": nx.community.modularity(
                    u.subgraph(nodes), pd.Series(p).groupby(pd.Series(p)).groups.values(), weight="weight"
                ),
            }
        )
    seed_nmi = [
        normalized_mutual_info_score(parts[i], parts[j]) for i in range(len(parts)) for j in range(i + 1, len(parts))
    ]
    dept_groups = pd.Series(dict(zip(nodes, truth))).groupby(truth).groups.values()
    lpa = list(nx.community.asyn_lpa_communities(u.subgraph(nodes), weight="weight", seed=SEED))
    lpa_lab = {n: i for i, c in enumerate(lpa) for n in c}
    r = pd.DataFrame(runs)
    # Resolution sweep. Picking the best value uses the labels, so the best row
    # is an optimistic upper bound, not something a deployment could achieve blind.
    sweep = []
    for res in (0.5, 1, 2, 4, 8, 16):
        p = louvain(u.subgraph(nodes), seed=SEED, resolution=res)
        lab = [p[n] for n in nodes]
        sweep.append(
            {
                "resolution": res,
                "n_communities": len(set(lab)),
                "nmi": normalized_mutual_info_score(truth, lab),
                "ari": adjusted_rand_score(truth, lab),
            }
        )
    return {
        "resolution_sweep": sweep,
        "n_nodes": len(nodes),
        "n_departments": len(set(truth)),
        "louvain_nmi_mean": r.nmi.mean(),
        "louvain_nmi_sd": r.nmi.std(),
        "louvain_ari_mean": r.ari.mean(),
        "louvain_ari_sd": r.ari.std(),
        "louvain_n_communities_mean": r.n_communities.mean(),
        "louvain_modularity_mean": r.modularity.mean(),
        "louvain_seed_to_seed_nmi_mean": float(np.mean(seed_nmi)),
        "label_propagation_nmi": normalized_mutual_info_score(truth, [lpa_lab[n] for n in nodes]),
        "label_propagation_ari": adjusted_rand_score(truth, [lpa_lab[n] for n in nodes]),
        "department_partition_modularity": nx.community.modularity(u.subgraph(nodes), dept_groups, weight="weight"),
    }


def reconstruct_departments(u: nx.Graph, dept: dict, fractions=(0.1, 0.3, 0.5, 0.8), repeats=10) -> pd.DataFrame:
    """Semi-supervised inference of department from structure alone.

    If a handful of known labels lets us recover everyone's department, the
    metadata encodes the formal organization (useful) - and the same fact is
    an attribute-inference risk (a privacy finding, not just a feature).
    """
    lcc = max(nx.connected_components(u), key=len)
    sizes = pd.Series({n: dept[n] for n in lcc}).value_counts()
    keep_depts = set(sizes[sizes >= MIN_GROUP].index)
    h = u.subgraph(lcc).copy()
    nodes = [n for n in h if dept[n] in keep_depts]
    y = np.array([dept[n] for n in nodes])
    a = nx.to_numpy_array(h, nodelist=list(h.nodes), weight="weight")
    emb_all = SpectralEmbedding(n_components=48, affinity="precomputed", random_state=SEED).fit_transform(a)
    idx = {n: i for i, n in enumerate(h.nodes)}
    x = emb_all[[idx[n] for n in nodes]]
    x = (x - x.mean(0)) / (x.std(0) + 1e-12)
    rows = []
    for p in fractions:
        for r in range(repeats):
            perm = rng.permutation(len(nodes))
            k = int(p * len(nodes))
            tr, te = perm[:k], perm[k:]
            known = {nodes[i]: y[i] for i in tr}
            # (a) weighted neighbour vote among labelled neighbours
            maj = pd.Series(y[tr]).mode()[0]
            pred_vote = []
            for i in te:
                votes: dict = {}
                for nb, ed in h[nodes[i]].items():
                    if nb in known:
                        votes[known[nb]] = votes.get(known[nb], 0) + ed["weight"]
                pred_vote.append(max(votes, key=votes.get) if votes else maj)
            # (b) logistic regression on spectral embedding
            clf = LogisticRegression(max_iter=3000, C=1.0)
            clf.fit(x[tr], y[tr])
            pred_lr = clf.predict(x[te])
            for name, pred in (("neighbour vote", pred_vote), ("spectral + logistic", pred_lr), ("majority class", [maj] * len(te))):
                rows.append(
                    {
                        "labelled_fraction": p,
                        "method": name,
                        "repeat": r,
                        "accuracy": float(np.mean(np.array(pred) == y[te])),
                        "macro_f1": f1_score(y[te], pred, average="macro", zero_division=0),
                    }
                )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Key-person dependency: what breaks when a few people leave?
# --------------------------------------------------------------------------
def removal_impact(u: nx.Graph, dept: dict, order: list, ks=(0, 1, 2, 5, 10, 20, 50)) -> list[dict]:
    cross = [(a, b) for a, b in u.edges if dept.get(a) != dept.get(b)]
    pairs_before = {tuple(sorted((dept[a], dept[b]))) for a, b in cross}
    out = []
    n0 = u.number_of_nodes()
    for k in ks:
        removed = set(order[:k])
        left = [(a, b) for a, b in cross if a not in removed and b not in removed]
        pairs_after = {tuple(sorted((dept[a], dept[b]))) for a, b in left}
        h = u.subgraph([n for n in u if n not in removed])
        lcc = max((len(c) for c in nx.connected_components(h)), default=0)
        out.append(
            {
                "k_removed": k,
                "pct_people_removed": 100 * k / n0,
                "pct_cross_dept_ties_lost": 100 * (1 - len(left) / len(cross)),
                "pct_dept_pairs_disconnected": 100 * (1 - len(pairs_after) / len(pairs_before)),
                "lcc_fraction": lcc / (n0 - k),
            }
        )
    return out


# --------------------------------------------------------------------------
# Temporal stability of "bottleneck" labels
# --------------------------------------------------------------------------
def centrality_stability(events: pd.DataFrame, period_weeks: int) -> pd.DataFrame:
    events = events.assign(period=events.week // period_weeks)
    full = events.period.value_counts()
    periods = sorted(p for p in full.index if (events.week[events.period == p].nunique() == period_weeks))
    cents = {}
    for p in periods:
        ev = events[events.period == p]
        g = nx.Graph()
        g.add_edges_from(ev[["src", "dst"]].itertuples(index=False, name=None))
        cents[p] = (
            pd.Series(dict(g.degree())),
            pd.Series(nx.betweenness_centrality(g, k=min(300, g.number_of_nodes()), seed=SEED)),
        )
    rows = []
    for p0, p1 in zip(periods[:-1], periods[1:]):
        for name, j in (("degree", 0), ("betweenness", 1)):
            a, b = cents[p0][j], cents[p1][j]
            common = a.index.intersection(b.index)
            rho = spearmanr(a[common], b[common]).statistic
            topn = max(5, int(0.05 * len(common)))
            ta = set(a[common].nlargest(topn).index)
            tb = set(b[common].nlargest(topn).index)
            rows.append(
                {
                    "period_weeks": period_weeks,
                    "from_period": p0,
                    "metric": name,
                    "spearman": rho,
                    "top5pct_jaccard": len(ta & tb) / len(ta | tb),
                    "top5pct_retained": len(ta & tb) / len(ta),
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def fig_department_map(u: nx.Graph, dept: dict, tab: pd.DataFrame) -> None:
    keep = set(tab.index)
    dg = nx.Graph()
    for d in keep:
        dg.add_node(d, size=tab.loc[d, "size"])
    for a, b in u.edges:
        da, db = dept[a], dept[b]
        if da != db and da in keep and db in keep:
            w = dg[da][db]["weight"] + 1 if dg.has_edge(da, db) else 1
            dg.add_edge(da, db, weight=w)
    pos = nx.spring_layout(dg, weight="weight", seed=SEED, k=0.9)
    fig, ax = plt.subplots(figsize=(8.5, 7))
    ws = np.array([dg[a][b]["weight"] for a, b in dg.edges])
    thr = np.quantile(ws, 0.6)
    strong = [(a, b) for a, b in dg.edges if dg[a][b]["weight"] >= thr]
    nx.draw_networkx_edges(
        dg, pos, edgelist=strong, width=[0.4 + 2.6 * dg[a][b]["weight"] / ws.max() for a, b in strong],
        edge_color=MUTED, ax=ax,
    )
    flagged = tab.index[tab.flag_silo_candidate | tab.flag_single_bridge]
    colors = [SERIES[1] if d in flagged else SERIES[0] for d in dg.nodes]
    nx.draw_networkx_nodes(
        dg, pos, node_size=[30 + 6 * dg.nodes[d]["size"] for d in dg.nodes], node_color=colors,
        edgecolors="#fcfcfb", linewidths=2, ax=ax,
    )
    nx.draw_networkx_labels(dg, pos, labels={d: f"D{d}" for d in dg.nodes}, font_size=7, font_color="#0b0b0b", ax=ax)
    ax.scatter([], [], s=60, color=SERIES[0], label="department (size = headcount)")
    ax.scatter([], [], s=60, color=SERIES[1], label="flagged: silo candidate or single-bridge dependency")
    ax.legend(loc="lower left")
    ax.set_title("Department-level collaboration map, email-Eu-core (strongest 40% of cross-department links)")
    ax.axis("off")
    save_fig(fig, EXP, "department_map")


def fig_lorenz(deg: pd.Series, bet: pd.Series) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    for i, (name, s) in enumerate((("email ties (degree)", deg), ("brokerage (betweenness)", bet))):
        v = np.sort(s.values)
        cum = np.concatenate([[0], np.cumsum(v) / v.sum()])
        x = np.linspace(0, 1, len(cum))
        ax.plot(x, cum, color=SERIES[i], label=f"{name}, Gini {gini(v):.2f}")
    ax.plot([0, 1], [0, 1], color=NEUTRAL, lw=1)
    ax.set_xlabel("share of people (sorted, lowest first)")
    ax.set_ylabel("cumulative share of total")
    ax.set_title("How concentrated is coordination?")
    ax.legend(loc="upper left")
    save_fig(fig, EXP, "lorenz_concentration")


def fig_openness(tab: pd.DataFrame) -> None:
    t = tab.sort_values("internal_lift")
    fig, ax = plt.subplots(figsize=(6.5, 7.5))
    colors = [SERIES[1] if f else SERIES[0] for f in t.flag_silo_candidate]
    ax.barh([f"D{d} (n={s})" for d, s in zip(t.index, t["size"])], t.internal_lift, color=colors, height=0.7)
    ax.axvline(1, color=NEUTRAL, lw=1)
    ax.set_xlabel("internal-tie lift (observed / expected under degree-preserving null)")
    ax.set_title("Inward orientation by department")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.barh([], [], color=SERIES[1], label="silo candidate (top-quartile lift and bottom-quartile reach)")
    ax.barh([], [], color=SERIES[0], label="other departments")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    save_fig(fig, EXP, "department_inwardness")


def fig_removal(curves: dict) -> None:
    fig, ax = plt.subplots(figsize=(6, 4.2))
    for i, (name, rows) in enumerate(curves.items()):
        df = pd.DataFrame(rows)
        ax.plot(df.pct_people_removed, df.pct_cross_dept_ties_lost, marker="o", ms=4, color=SERIES[i], label=name)
    ax.set_xlabel("% of people removed")
    ax.set_ylabel("% of cross-department ties lost")
    ax.set_title("Key-person dependency: coordination lost when people leave")
    ax.legend()
    save_fig(fig, EXP, "key_person_removal")


def fig_reconstruction(res: pd.DataFrame, label: str, name: str) -> None:
    s = res.groupby(["method", "labelled_fraction"]).accuracy.agg(["mean", "std"]).reset_index()
    fig, ax = plt.subplots(figsize=(5.8, 4.2))
    for i, m in enumerate(["neighbour vote", "spectral + logistic", "majority class"]):
        d = s[s.method == m]
        c = NEUTRAL if m == "majority class" else SERIES[i]
        ax.errorbar(d.labelled_fraction * 100, d["mean"], yerr=d["std"], color=c, marker="o", ms=4, capsize=3, label=m)
    ax.set_ylim(0, 1)
    ax.set_xlabel("% of people whose department is known")
    ax.set_ylabel("accuracy on the rest")
    ax.set_title(f"Recovering departments from {label} alone")
    ax.legend(loc="lower right")
    save_fig(fig, EXP, name)


def fig_stability(stab: pd.DataFrame) -> None:
    s = stab.groupby(["period_weeks", "metric"])[["spearman", "top5pct_retained"]].mean().reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, col, title in zip(axes, ["spearman", "top5pct_retained"], ["rank correlation, consecutive periods", "share of top-5% still top-5% next period"]):
        for i, m in enumerate(["degree", "betweenness"]):
            d = s[s.metric == m]
            ax.plot(d.period_weeks, d[col], marker="o", ms=5, color=SERIES[i], label=m)
        ax.set_xlabel("snapshot length (weeks)")
        ax.set_title(title, fontsize=9.5)
        ax.set_ylim(0, 1)
    axes[0].legend()
    fig.suptitle("Are 'bottleneck' labels stable over time? (email-Eu-core-temporal)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save_fig(fig, EXP, "centrality_stability")


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    metrics: dict = {}

    # ---- A. static email network with ground-truth departments -----------
    g, dept = load_eu_core_static()
    u = to_weighted_undirected(g)
    nx.set_node_attributes(u, dept, "dept")
    lwcc = max(nx.weakly_connected_components(g), key=len)
    metrics["network"] = {
        "people": g.number_of_nodes(),
        "directed_ties": g.number_of_edges(),
        "isolated_people": sum(1 for n in g if g.degree(n) == 0),
        "density": nx.density(g),
        "reciprocity": nx.reciprocity(g),
        "largest_component_share": len(lwcc) / g.number_of_nodes(),
        "departments": len(set(dept.values())),
        "departments_with_at_least_5": int((pd.Series(dept).value_counts() >= MIN_GROUP).sum()),
        "department_assortativity": nx.attribute_assortativity_coefficient(u, "dept"),
    }

    deg = pd.Series(dict(u.degree()))
    bet = pd.Series(nx.betweenness_centrality(g))
    active = deg[deg > 0].index
    deg, bet = deg[active], bet[active]
    metrics["concentration"] = {
        "degree_gini": gini(deg),
        "betweenness_gini": gini(bet),
        "top1pct_share_of_betweenness": bet.nlargest(max(1, len(bet) // 100)).sum() / bet.sum(),
        "top5pct_share_of_betweenness": bet.nlargest(len(bet) // 20).sum() / bet.sum(),
        "top5pct_share_of_ties": deg.nlargest(len(deg) // 20).sum() / deg.sum(),
        "articulation_points": len(list(nx.articulation_points(u.subgraph(active)))),
        "spearman_degree_vs_betweenness": spearmanr(deg, bet).statistic,
    }
    fig_lorenz(deg, bet)

    tab = flag_departments(department_table(u, dept))
    save_table(tab.round(4), EXP, "department_indicators")
    metrics["departments"] = {
        "reported_departments": len(tab),
        "median_internal_lift": tab.internal_lift.median(),
        "silo_candidates": [int(d) for d in tab.index[tab.flag_silo_candidate]],
        "single_bridge_departments": [int(d) for d in tab.index[tab.flag_single_bridge]],
        "median_people_for_80pct_external": tab.people_for_80pct_external.median(),
        "spearman_size_vs_lift": spearmanr(tab["size"], tab.internal_lift).statistic,
    }
    fig_department_map(u, dept, tab)
    fig_openness(tab)

    metrics["communities_vs_departments_email"] = community_vs_departments(u, dept)
    rec = reconstruct_departments(u, dept)
    save_table(rec.groupby(["method", "labelled_fraction"])[["accuracy", "macro_f1"]].agg(["mean", "std"]).round(4), EXP, "department_reconstruction_email")
    metrics["department_reconstruction_email"] = (
        rec.groupby(["method", "labelled_fraction"]).accuracy.mean().unstack(0).round(4).to_dict()
    )
    fig_reconstruction(rec, "email metadata", "department_reconstruction_email")

    order_bet = list(bet.sort_values(ascending=False).index)
    order_deg = list(deg.sort_values(ascending=False).index)
    rand_curves = []
    for r in range(10):
        rand_curves.append(pd.DataFrame(removal_impact(u, dept, list(rng.permutation(list(active))))))
    rand_mean = pd.concat(rand_curves).groupby("k_removed").mean().reset_index().to_dict("records")
    curves = {
        "highest brokerage first": removal_impact(u, dept, order_bet),
        "most ties first": removal_impact(u, dept, order_deg),
        "random (mean of 10)": rand_mean,
    }
    metrics["key_person_removal"] = {k: v for k, v in curves.items()}
    fig_removal(curves)

    # ---- B. stability over time --------------------------------------------
    ev = load_eu_core_temporal()
    stab = pd.concat([centrality_stability(ev, w) for w in (1, 4, 13)], ignore_index=True)
    save_table(stab.round(4), EXP, "centrality_stability")
    metrics["centrality_stability"] = (
        stab.groupby(["period_weeks", "metric"])[["spearman", "top5pct_jaccard", "top5pct_retained"]].mean().round(4).reset_index().to_dict("records")
    )
    fig_stability(stab)

    # ---- C. replication on face-to-face contacts ---------------------------
    tij, sp_dept = load_sociopatterns_workplace()
    pairs = np.sort(tij[["i", "j"]].to_numpy(), axis=1)
    w = pd.DataFrame(pairs, columns=["a", "b"]).value_counts().reset_index(name="weight")
    sp = nx.Graph()
    sp.add_nodes_from(sp_dept)
    sp.add_weighted_edges_from(w.itertuples(index=False, name=None))
    metrics["sociopatterns"] = {
        "people": sp.number_of_nodes(),
        "contact_pairs": sp.number_of_edges(),
        "contact_events_20s": len(tij),
        "departments": pd.Series(sp_dept).value_counts().to_dict(),
        "communities_vs_departments": community_vs_departments(sp, sp_dept),
    }
    sp_tab = flag_departments(department_table(sp, sp_dept))
    save_table(sp_tab.round(4), EXP, "department_indicators_sociopatterns")
    metrics["sociopatterns"]["department_indicators"] = sp_tab.round(3).reset_index().to_dict("records")
    sp_rec = reconstruct_departments(sp, sp_dept, fractions=(0.1, 0.3, 0.5), repeats=10)
    metrics["department_reconstruction_sociopatterns"] = (
        sp_rec.groupby(["method", "labelled_fraction"]).accuracy.mean().unstack(0).round(4).to_dict()
    )
    fig_reconstruction(sp_rec, "face-to-face contacts", "department_reconstruction_f2f")

    save_json(metrics, EXP)
    print(pd.Series({k: v for k, v in metrics["concentration"].items()}))
    print(metrics["communities_vs_departments_email"])
    print(metrics["departments"])


if __name__ == "__main__":
    main()

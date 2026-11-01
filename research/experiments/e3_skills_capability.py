"""Experiment 3 - Skills and organizational capability analysis.

Research questions
    RQ3a  Can free-text descriptions of work (task statements standing in for
          tickets, documents or AI-assistant requests) be mapped to the right
          occupational profile, and therefore to its required skills?  How
          accurate is that mapping from one artifact versus several?
    RQ3b  Given role requirements, can a team-level capability view expose
          skill gaps and single-holder ("bus factor 1") skills without
          ranking people?
    RQ3c  Can aggregated AI-assistant usage be mapped onto the same task
          taxonomy, as a privacy-preserving signal of where AI is used?

Data
    * O*NET 31.0 (real, US DOL, CC BY 4.0): 18,838 task statements for 923
      occupations; importance/level ratings for 35 skills.
    * Anthropic Economic Index, release 2025-02-10 (real, aggregated, MIT licence):
      share of Claude conversations mapped to each O*NET task.
    * Team members' declared skill levels in Part B are SYNTHETIC (generated
      here and labelled as such). No real employee data is used.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.preprocessing import normalize  # noqa: E402

from hrnexus.common import CRITICAL, ROOT, SEED, SERIES, save_fig, save_json, save_table, setup_style  # noqa: E402
from hrnexus.data import load_anthropic_ei, load_onet  # noqa: E402

EXP = "e3_skills"
rng = np.random.default_rng(SEED)

TEAM = {  # role -> headcount, for a hypothetical digital product team
    "15-1252.00": 4,  # Software Developers
    "15-1253.00": 2,  # Software QA Analysts and Testers
    "15-2051.00": 2,  # Data Scientists
    "15-1255.00": 1,  # Web and Digital Interface Designers
    "15-1212.00": 1,  # Information Security Analysts
    "13-1082.00": 1,  # Project Management Specialists
    "15-1242.00": 1,  # Database Administrators
}


# --------------------------------------------------------------------------
# A. text -> occupation -> skills
# --------------------------------------------------------------------------
def split_tasks(tasks: pd.DataFrame, min_tasks: int = 8, test_frac: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame]:
    t = tasks[["O*NET-SOC Code", "Task"]].rename(columns={"O*NET-SOC Code": "occ", "Task": "text"})
    t = t[t.groupby("occ").occ.transform("size") >= min_tasks]
    t = t.assign(r=rng.random(len(t)))
    t["rank"] = t.groupby("occ").r.rank(pct=True)
    return t[t["rank"] > test_frac].drop(columns=["r", "rank"]), t[t["rank"] <= test_frac].drop(columns=["r", "rank"])


def embed_tfidf(train: pd.DataFrame, test: pd.DataFrame):
    vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, stop_words="english")
    xtr = vec.fit_transform(train.text)
    return normalize(xtr), normalize(vec.transform(test.text))


def embed_minilm(train: pd.DataFrame, test: pd.DataFrame):
    from sentence_transformers import SentenceTransformer

    cache = ROOT / "data" / "cache" / "minilm_onet31_tasks.npz"
    allt = pd.concat([train.text, test.text]).drop_duplicates()
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        lookup = dict(zip(z["text"], z["emb"]))
    else:
        m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
        emb = m.encode(list(allt), batch_size=128, normalize_embeddings=True, show_progress_bar=False)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, text=np.array(list(allt), dtype=object), emb=emb)
        lookup = dict(zip(allt, emb))
    return np.vstack([lookup[t] for t in train.text]), np.vstack([lookup[t] for t in test.text])


def centroids(x, labels: np.ndarray, classes: np.ndarray):
    rows = []
    for c in classes:
        v = x[labels == c].mean(axis=0)
        rows.append(np.asarray(v).ravel())
    c = np.vstack(rows)
    return c / np.linalg.norm(c, axis=1, keepdims=True)


def evaluate_mapping(xtr, xte, train, test, bag_sizes=(1, 3, 5), repeats=200) -> tuple[pd.DataFrame, dict]:
    classes = np.array(sorted(train.occ.unique()))
    cent = centroids(xtr, train.occ.values, classes)
    xte_d = xte.toarray() if hasattr(xte, "toarray") else xte
    rows, preds = [], {}
    yte = test.occ.values
    for k in bag_sizes:
        if k == 1:
            q, truth = xte_d, yte
        else:  # bags of k artifacts from the same occupation
            qs, truth = [], []
            for occ, idx in test.groupby("occ").indices.items():
                if len(idx) < k:
                    continue
                for _ in range(3):
                    pick = rng.choice(idx, size=k, replace=False)
                    qs.append(xte_d[pick].mean(axis=0))
                    truth.append(occ)
            q, truth = np.vstack(qs), np.array(truth)
        sims = q @ cent.T
        order = np.argsort(-sims, axis=1)
        ranks = np.array([np.where(classes[o] == t)[0][0] for o, t in zip(order, truth)])
        rows.append({"artifacts": k, "n_queries": len(truth), "top1": np.mean(ranks == 0), "top5": np.mean(ranks < 5),
                     "top10": np.mean(ranks < 10), "median_rank": float(np.median(ranks + 1))})
        preds[k] = (truth, classes[order[:, 0]])
    return pd.DataFrame(rows), preds


def skill_matrix(skills: pd.DataFrame, scale: str = "IM") -> pd.DataFrame:
    s = skills[skills["Scale ID"] == scale]
    return s.pivot_table(index="O*NET-SOC Code", columns="Element Name", values="Data Value")


def profile_fidelity(truth, pred, im: pd.DataFrame) -> dict:
    ok = [(t, p) for t, p in zip(truth, pred) if t in im.index and p in im.index]
    t_m = im.loc[[t for t, _ in ok]].values
    p_m = im.loc[[p for _, p in ok]].values
    r = np.array([np.corrcoef(a, b)[0, 1] for a, b in zip(t_m, p_m)])
    mae = np.abs(t_m - p_m).mean(axis=1)

    def top5(v):
        return set(np.argsort(-v)[:5])

    jac = np.array([len(top5(a) & top5(b)) / len(top5(a) | top5(b)) for a, b in zip(t_m, p_m)])
    rand = im.values[rng.integers(0, len(im), size=len(t_m))]
    mean_prof = np.tile(im.values.mean(0), (len(t_m), 1))
    return {
        "n": len(ok),
        "profile_pearson_mean": float(np.nanmean(r)),
        "profile_mae_mean": float(mae.mean()),
        "top5_skill_jaccard_mean": float(jac.mean()),
        "baseline_random_occupation_mae": float(np.abs(t_m - rand).mean()),
        "baseline_average_profile_mae": float(np.abs(t_m - mean_prof).mean()),
        "baseline_random_occupation_pearson": float(np.nanmean([np.corrcoef(a, b)[0, 1] for a, b in zip(t_m, rand)])),
    }


# --------------------------------------------------------------------------
# B. team capability (synthetic people, real role requirements)
# --------------------------------------------------------------------------
def coverage(roster: pd.DataFrame, req: pd.Series) -> pd.DataFrame:
    meets = roster[req.index].ge(req - 0.5)  # within half a level of the requirement counts as meeting it
    near = roster[req.index].ge(req - 1.5) & ~meets
    cov = pd.DataFrame({"required_level": req.round(2), "holders": meets.sum(), "within_one_level": near.sum()})
    cov["status"] = np.where(cov.holders == 0, "gap", np.where(cov.holders == 1, "single holder", "covered"))
    return cov


def team_capability(skills: pd.DataFrame, knowledge: pd.DataFrame, occ_titles: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    both = pd.concat([skills, knowledge.assign(**{"Element Name": "K: " + knowledge["Element Name"]})])
    im, lv = skill_matrix(both, "IM"), skill_matrix(both, "LV")
    # team requirement: for each skill rated important (IM >= 3.5) by any role, the highest level any role needs
    req = {}
    for occ in TEAM:
        for sk in im.columns:
            if im.loc[occ, sk] >= 3.5:
                req[sk] = max(req.get(sk, 0), lv.loc[occ, sk])
    req = pd.Series(req).sort_values(ascending=False)
    people = []
    pid = 0
    for occ, n in TEAM.items():
        for _ in range(n):
            pid += 1
            # SYNTHETIC: declared level = role's O*NET level + noise; some people stronger/weaker
            levels = np.clip(lv.loc[occ, req.index].values + rng.normal(-0.2, 0.7, len(req)) + rng.normal(0, 0.4), 0, 7)
            people.append(pd.Series(levels, index=req.index, name=f"P{pid:02d}"))
    roster = pd.DataFrame(people)
    roles = pd.Series({f"P{i + 1:02d}": o for i, o in enumerate([o for o, n in TEAM.items() for _ in range(n)])})
    cov = coverage(roster, req)
    # what-if: one person in a given role leaves (the first holder of that role)
    scen = [{"scenario": "current team", "gaps": int((cov.status == "gap").sum()), "single_holder": int((cov.status == "single holder").sum())}]
    for occ in TEAM:
        leaver = roles[roles == occ].index[0]
        c = coverage(roster.drop(index=leaver), req)
        scen.append({"scenario": f"one {occ_titles[occ]} leaves", "gaps": int((c.status == "gap").sum()),
                     "single_holder": int((c.status == "single holder").sum()),
                     "new_gaps": ", ".join(sorted(set(c.index[c.status == "gap"]) - set(cov.index[cov.status == "gap"])))})
    return cov, roster.assign(role=roles.map(occ_titles)), pd.DataFrame(scen)


# --------------------------------------------------------------------------
# C. AI usage mapped to the team's tasks (aggregated public data)
# --------------------------------------------------------------------------
def ai_usage_by_role(tasks: pd.DataFrame, ei: pd.DataFrame, occ_titles: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    t = tasks.assign(key=tasks.Task.str.lower().str.strip())
    e = ei.assign(key=ei.task_name.str.lower().str.strip())
    match_rate = float(e.key.isin(set(t.key)).mean())
    m = t.merge(e[["key", "pct"]], on="key", how="left")
    rows, top = [], []
    for occ in TEAM:
        d = m[m["O*NET-SOC Code"] == occ]
        rows.append({"role": occ_titles[occ], "tasks": len(d), "tasks_seen_in_ai_usage": int(d.pct.notna().sum()),
                     "share_of_tasks_seen": float(d.pct.notna().mean()), "pct_of_all_conversations": float(d.pct.sum())})
        for _, r in d.dropna(subset=["pct"]).nlargest(3, "pct").iterrows():
            top.append({"role": occ_titles[occ], "task": r.Task, "pct_of_all_conversations": r.pct})
    return pd.DataFrame(rows), pd.DataFrame(top), match_rate


# --------------------------------------------------------------------------
def fig_mapping(res: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 4))
    for i, (m, g) in enumerate(res.groupby("method", sort=False)):
        ax.plot(g.artifacts, g.top1, marker="o", ms=5, color=SERIES[i], label=f"{m}: top-1")
        ax.plot(g.artifacts, g.top5, marker="s", ms=5, color=SERIES[i], lw=1.2, alpha=0.6, label=f"{m}: top-5")
    ax.set_ylim(0, 1)
    ax.set_xticks([1, 3, 5])
    ax.set_xlabel("work artifacts available (task descriptions)")
    ax.set_ylabel(f"accuracy over {res.n_classes.iloc[0]} occupations")
    ax.set_title("Mapping work descriptions to occupational skill profiles")
    ax.legend(fontsize=7.5, loc="lower right")
    save_fig(fig, EXP, "text_to_occupation")


def fig_coverage(cov: pd.DataFrame) -> None:
    c = cov.sort_values("required_level")
    colors = {"covered": SERIES[0], "single holder": SERIES[3], "gap": CRITICAL}
    fig, ax = plt.subplots(figsize=(7, 0.26 * len(c) + 1.4))
    ax.barh(c.index, c.holders, color=[colors[s] for s in c.status], height=0.7)
    for y, (h, s) in enumerate(zip(c.holders, c.status)):
        if s != "covered":
            ax.text(h + 0.1, y, "! " + s, va="center", fontsize=7, color="#0b0b0b")
    ax.set_xlabel("team members meeting the required level (synthetic profiles)")
    ax.set_title("Team capability coverage, skills ordered by required level")
    ax.tick_params(axis="y", labelsize=7.5)
    for k, v in colors.items():
        ax.barh([], [], color=v, label=k)
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    save_fig(fig, EXP, "team_skill_coverage")


# --------------------------------------------------------------------------
def main() -> None:
    setup_style()
    o = load_onet()
    occ_titles = o["occupations"].set_index("O*NET-SOC Code").Title
    metrics: dict = {}

    train, test = split_tasks(o["tasks"])
    metrics["corpus"] = {"occupations": int(train.occ.nunique()), "train_tasks": len(train), "test_tasks": len(test)}
    im = skill_matrix(o["skills"], "IM")
    results, fidelity = [], {}
    methods = [("TF-IDF", embed_tfidf)]
    try:
        import sentence_transformers  # noqa: F401

        methods.append(("MiniLM sentence embeddings", embed_minilm))
    except ImportError:
        print("sentence-transformers not installed: TF-IDF only")
    for name, fn in methods:
        xtr, xte = fn(train, test)
        r, preds = evaluate_mapping(xtr, xte, train, test)
        r["method"] = name
        r["n_classes"] = train.occ.nunique()
        results.append(r)
        fidelity[name] = {f"{k}_artifacts": profile_fidelity(*preds[k], im) for k in preds}
    res = pd.concat(results, ignore_index=True)
    save_table(res.round(4), EXP, "text_to_occupation")
    metrics["text_to_occupation"] = res.round(4).to_dict("records")
    metrics["skill_profile_fidelity"] = fidelity
    fig_mapping(res)

    cov, roster, scen = team_capability(o["skills"], o["knowledge"], occ_titles)
    save_table(cov, EXP, "team_skill_coverage")
    save_table(scen, EXP, "team_departure_scenarios")
    metrics["departure_scenarios"] = scen.to_dict("records")
    metrics["team_capability"] = {
        "team_size": int(sum(TEAM.values())),
        "skills_required": len(cov),
        "gaps": cov.index[cov.status == "gap"].tolist(),
        "single_holder_skills": cov.index[cov.status == "single holder"].tolist(),
        "development_pool_for_flagged": cov.loc[cov.status != "covered", "within_one_level"].to_dict(),
        "note": "member skill levels are synthetic; requirements are real O*NET 31.0 ratings",
    }
    fig_coverage(cov)

    usage, top, match = ai_usage_by_role(o["tasks"], load_anthropic_ei(), occ_titles)
    save_table(usage.round(5), EXP, "ai_usage_by_role")
    save_table(top, EXP, "ai_usage_top_tasks")
    metrics["ai_usage"] = {"ei_tasks_matched_to_onet31": match, "by_role": usage.round(5).to_dict("records"), "top_tasks": top.round(5).to_dict("records")}

    save_json(metrics, EXP)
    print(res)
    print(pd.DataFrame({m: {k: v["profile_mae_mean"] for k, v in f.items()} for m, f in fidelity.items()}))
    print(fidelity)
    print(cov)
    print(scen.to_string())
    print(usage)


if __name__ == "__main__":
    main()

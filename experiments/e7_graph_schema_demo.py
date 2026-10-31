"""Organizational relationship graph: schema, example instance and team profiles.

SYNTHETIC EXAMPLE. The graph below is generated to illustrate the proposed
schema (Employee, Team, Role, Project, Task, Skill, KnowledgeResource) and the
team-level analytics it supports. It contains no real people.

What it demonstrates
    * a typed, time-stamped property graph that links people to work, skills
      and knowledge, so questions such as "which cross-team dependencies hang on
      one person?" become graph queries;
    * explainable team profiles that describe work conditions and structure
      with provenance and caveats - and deliberately contain no individual
      scores and no psychological inferences.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from hrnexus.common import MIN_GROUP, MUTED, SEED, SERIES, out_dir, save_fig, setup_style  # noqa: E402

EXP = "e7_graph_schema"
rng = np.random.default_rng(SEED)

NODE_TYPES = {
    "Team": SERIES[0], "Employee": SERIES[6], "Project": SERIES[1], "Task": SERIES[3],
    "Skill": SERIES[2], "KnowledgeResource": SERIES[4],
}
# (source type, relation, target type, evidence source)
SCHEMA = [
    ("Employee", "MEMBER_OF", "Team", "HRIS"),
    ("Employee", "ASSIGNED_TO", "Task", "task tracker"),
    ("Task", "PART_OF", "Project", "task tracker"),
    ("Task", "DEPENDS_ON", "Task", "task tracker"),
    ("Task", "REQUIRES", "Skill", "task template / O*NET mapping"),
    ("Employee", "HAS_SKILL", "Skill", "self-declared + verified (consented)"),
    ("Employee", "COLLABORATES_WITH", "Employee", "email/chat/meeting metadata, aggregated weekly"),
    ("Task", "USES", "KnowledgeResource", "document links / wiki metadata"),
    ("Employee", "HANDS_OFF_TO", "Employee", "task status transitions"),
]


def build() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    teams = ["Platform", "Data", "Product", "Support"]
    skills = ["Python", "Kubernetes", "SQL", "Security review", "UX research", "Customer escalation", "Data modelling", "Release mgmt"]
    team_skills = {
        "Platform": ["Python", "Kubernetes", "Release mgmt", "Security review"],
        "Data": ["Python", "SQL", "Data modelling"],
        "Product": ["UX research", "Release mgmt"],
        "Support": ["Customer escalation", "SQL"],
    }
    docs = ["Runbook: deploy", "Data dictionary", "Design system", "Escalation guide", "Security checklist"]
    for t in teams:
        g.add_node(t, type="Team")
    for s in skills:
        g.add_node(s, type="Skill")
    for d in docs:
        g.add_node(d, type="KnowledgeResource")
    emp = []
    for t in teams:
        for i in range(6):
            e = f"{t[:2].upper()}-{i + 1}"
            emp.append((e, t))
            g.add_node(e, type="Employee", team=t)
            g.add_edge(e, t, rel="MEMBER_OF", valid_from="2026-01-01")
            for s in team_skills[t]:
                if rng.random() < 0.55:
                    g.add_edge(e, s, rel="HAS_SKILL", source="self-declared", verified=bool(rng.random() < 0.5))
    # one deliberate single-holder skill: only PL-1 can do security reviews
    for e, _ in emp:
        if g.has_edge(e, "Security review"):
            g.remove_edges_from([(e, "Security review", k) for k in list(g[e]["Security review"])])
    g.add_edge("PL-1", "Security review", rel="HAS_SKILL", source="certification", verified=True)

    projects = {"Checkout revamp": ["Product", "Platform", "Data"], "Data platform v2": ["Data", "Platform"], "Support bot": ["Support", "Data", "Product"]}
    task_id = 0
    for p, ts in projects.items():
        g.add_node(p, type="Project")
        prev = None
        for t in ts:
            for _ in range(3):
                task_id += 1
                k = f"T{task_id:02d}"
                g.add_node(k, type="Task", week=int(rng.integers(30, 40)), status=str(rng.choice(["done", "in progress", "blocked"], p=[0.6, 0.3, 0.1])))
                g.add_edge(k, p, rel="PART_OF")
                members = [e for e, tt in emp if tt == t]
                g.add_edge(str(rng.choice(members)), k, rel="ASSIGNED_TO")
                need = str(rng.choice(team_skills[t]))
                g.add_edge(k, need, rel="REQUIRES")
                if prev is not None and rng.random() < 0.7:
                    g.add_edge(k, prev, rel="DEPENDS_ON")
                if rng.random() < 0.5:
                    g.add_edge(k, str(rng.choice(docs)), rel="USES")
                prev = k
    # every release in Checkout needs a security review by the single holder
    for k in ("T01", "T04", "T07"):
        g.add_edge(k, "Security review", rel="REQUIRES")
        g.add_edge("PL-1", k, rel="ASSIGNED_TO")
    # weekly-aggregated collaboration edges (counts, not content)
    for a, ta in emp:
        for b, tb in emp:
            if a < b and rng.random() < (0.45 if ta == tb else 0.04):
                g.add_edge(a, b, rel="COLLABORATES_WITH", weekly_interactions=int(rng.integers(1, 20)), week="2026-W39")
    return g


def team_profile(g: nx.MultiDiGraph, team: str) -> dict:
    members = [n for n, d in g.nodes(data=True) if d.get("type") == "Employee" and d.get("team") == team]
    if len(members) < MIN_GROUP:
        return {"team": team, "suppressed": True, "reason": f"fewer than {MIN_GROUP} members"}
    tasks = {v for m in members for _, v, d in g.out_edges(m, data=True) if d["rel"] == "ASSIGNED_TO"}
    # cross-team dependencies: a task of this team depends on / is depended on by another team's task
    owner = {v: g.nodes[u]["team"] for u, v, d in g.edges(data=True) if d["rel"] == "ASSIGNED_TO"}
    cross = [(u, v) for u, v, d in g.edges(data=True) if d["rel"] == "DEPENDS_ON" and (owner.get(u) == team) != (owner.get(v) == team)]
    req = {v for t in tasks for _, v, d in g.out_edges(t, data=True) if d["rel"] == "REQUIRES"}
    holders = {s: [u for u, _, d in g.in_edges(s, data=True) if d["rel"] == "HAS_SKILL"] for s in req}
    single = sorted(s for s, h in holders.items() if len(h) == 1)
    gap = sorted(s for s, h in holders.items() if len(h) == 0)
    collab = [(u, v, d["weekly_interactions"]) for u, v, d in g.edges(data=True) if d["rel"] == "COLLABORATES_WITH" and (u in members or v in members)]
    external = sum(w for u, v, w in collab if (u in members) != (v in members))
    total = sum(w for _, _, w in collab)
    blocked = sum(1 for t in tasks if g.nodes[t].get("status") == "blocked")
    return {
        "team": team,
        "period": "2026-W30..W39 (synthetic)",
        "headcount": len(members),
        "work": {"tasks_in_period": len(tasks), "blocked_tasks": blocked},
        "coordination": {
            "cross_team_dependencies": len(cross),
            "external_share_of_collaboration": round(external / total, 3) if total else None,
        },
        "capability": {"skills_required_by_tasks": sorted(req), "single_holder_skills": single, "unheld_skills": gap},
        "provenance": ["HRIS membership", "task tracker (assignment, status, dependency)", "collaboration metadata aggregated weekly, no content"],
        "caveats": [
            "describes work structure, not individual performance",
            "single-holder status reflects declared/verified skills, which may be incomplete",
            "collaboration volume is not a measure of value or quality",
        ],
        "deliberately_absent": ["individual scores or rankings", "inferred stress, mood or health", "message content"],
    }


def draw(g: nx.MultiDiGraph) -> None:
    layer = {"Team": 0, "Employee": 1, "Task": 2, "Project": 3, "Skill": 4, "KnowledgeResource": 5}
    h = nx.DiGraph()
    for n, d in g.nodes(data=True):
        h.add_node(n, layer=layer[d["type"]], type=d["type"])
    for u, v, d in g.edges(data=True):
        if d["rel"] != "COLLABORATES_WITH":
            h.add_edge(u, v, rel=d["rel"])
    pos = nx.multipartite_layout(h, subset_key="layer", align="vertical", scale=2)
    fig, ax = plt.subplots(figsize=(12, 8.5))
    hi = {("PL-1", "Security review"), ("T01", "Security review"), ("T04", "Security review"), ("T07", "Security review"),
          ("PL-1", "T01"), ("PL-1", "T04"), ("PL-1", "T07")}
    normal = [e for e in h.edges if e not in hi]
    nx.draw_networkx_edges(h, pos, edgelist=normal, edge_color=MUTED, width=0.6, arrows=False, ax=ax)
    nx.draw_networkx_edges(h, pos, edgelist=[e for e in h.edges if e in hi], edge_color=SERIES[7], width=2, arrows=False, ax=ax)
    for t, c in NODE_TYPES.items():
        nodes = [n for n, d in h.nodes(data=True) if d["type"] == t]
        nx.draw_networkx_nodes(h, pos, nodelist=nodes, node_color=c, node_size=150 if t in ("Employee", "Task") else 320,
                               edgecolors="#fcfcfb", linewidths=1.5, ax=ax, label=t)
    labels = {n: n for n, d in h.nodes(data=True) if d["type"] in ("Team", "Project", "Skill", "KnowledgeResource")}
    nx.draw_networkx_labels(h, pos, labels=labels, font_size=7.5, ax=ax, verticalalignment="bottom")
    ax.plot([], [], color=SERIES[7], lw=2, label="single-holder dependency (PL-1 -> Security review)")
    ax.legend(loc="lower center", ncol=4, fontsize=8, bbox_to_anchor=(0.5, -0.06))
    ax.set_title("Synthetic organizational graph: Team | Employee | Task | Project | Skill | Knowledge resource")
    ax.axis("off")
    save_fig(fig, EXP, "org_graph_example")


def main() -> None:
    setup_style()
    g = build()
    draw(g)
    counts = pd.Series([d["type"] for _, d in g.nodes(data=True)]).value_counts().to_dict()
    rels = pd.Series([d["rel"] for _, _, d in g.edges(data=True)]).value_counts().to_dict()
    profiles = [team_profile(g, t) for t in ("Platform", "Data", "Product", "Support")]
    d = out_dir(EXP)
    (d / "team_profiles.json").write_text(json.dumps(profiles, indent=2))
    (d / "schema.json").write_text(json.dumps({"nodes": list(NODE_TYPES), "edges": [
        {"from": a, "rel": r, "to": b, "evidence": e} for a, r, b, e in SCHEMA]}, indent=2))
    (d / "metrics.json").write_text(json.dumps({"node_counts": counts, "edge_counts": rels}, indent=2))
    print(counts, rels)
    print(json.dumps(profiles[0], indent=2))


if __name__ == "__main__":
    main()

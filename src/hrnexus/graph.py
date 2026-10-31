"""Graph helpers shared by the collaboration, workload and early-risk experiments."""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from .common import SEED


def to_weighted_undirected(g: nx.DiGraph) -> nx.Graph:
    """Collapse a directed graph: weight 2 for reciprocated pairs, 1 otherwise."""
    u = nx.Graph()
    u.add_nodes_from(g.nodes)
    for a, b in g.edges:
        if u.has_edge(a, b):
            u[a][b]["weight"] += 1
        else:
            u.add_edge(a, b, weight=1)
    return u


def events_to_graph(events: pd.DataFrame) -> nx.Graph:
    """Undirected graph weighted by message count from (src, dst) events."""
    pairs = np.sort(events[["src", "dst"]].to_numpy(), axis=1)
    w = pd.DataFrame(pairs, columns=["a", "b"]).value_counts().reset_index(name="weight")
    g = nx.Graph()
    g.add_weighted_edges_from(w.itertuples(index=False, name=None))
    return g


def louvain(g: nx.Graph, seed: int = SEED, resolution: float = 1.0) -> dict[int, int]:
    comms = nx.community.louvain_communities(g, weight="weight", seed=seed, resolution=resolution)
    comms = sorted(comms, key=len, reverse=True)
    return {n: i for i, c in enumerate(comms) for n in c}


def infer_units(events: pd.DataFrame, min_size: int = 5, seed: int = SEED, resolution: float = 4.0) -> dict[int, int]:
    """Infer working units from communication structure when no org chart is joinable.

    resolution=4 is the Louvain setting whose granularity best matched the
    real departments of the labelled email-Eu-core graph in Experiment 2
    (that choice used the labels, so treat units as department-sized proxies).
    Units smaller than ``min_size`` are pooled into unit -1 so that every
    reported unit satisfies the aggregation threshold.
    """
    part = louvain(events_to_graph(events), seed=seed, resolution=resolution)
    sizes = pd.Series(part).value_counts()
    return {n: (u if sizes[u] >= min_size else -1) for n, u in part.items()}

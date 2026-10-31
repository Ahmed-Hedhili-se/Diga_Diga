"""Statistics for honest k/n reporting (P2)."""
from __future__ import annotations

from itertools import combinations

from scipy.stats import beta


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1-alpha) interval for a binomial proportion."""
    if n <= 0:
        raise ValueError("n must be > 0")
    if not 0 <= k <= n:
        raise ValueError("need 0 <= k <= n")
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lo, hi


def rate(k: int, n: int) -> dict:
    """Uniform shape for summary.json and the metrics slide: '3/40 (7.5%, 95% CI 1.6–20.4%)'."""
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "ci95": None, "text": "n/a (0 runs)"}
    lo, hi = clopper_pearson(k, n)
    return {"k": k, "n": n, "rate": k / n, "ci95": [lo, hi],
            "text": f"{k}/{n} ({100 * k / n:.1f}%, 95% CI {100 * lo:.1f}–{100 * hi:.1f}%)"}


def kendall_tau(a: list, b: list) -> float:
    """Kendall tau-b between two rankings given as score lists over the same items."""
    if len(a) != len(b) or len(a) < 2:
        raise ValueError("need two equal-length lists of >= 2")
    conc = disc = ties_a = ties_b = 0
    for i, j in combinations(range(len(a)), 2):
        da, db = a[i] - a[j], b[i] - b[j]
        if da == 0 and db == 0:
            continue
        if da == 0:
            ties_a += 1
        elif db == 0:
            ties_b += 1
        elif (da > 0) == (db > 0):
            conc += 1
        else:
            disc += 1
    denom = ((conc + disc + ties_a) * (conc + disc + ties_b)) ** 0.5
    return (conc - disc) / denom if denom else 0.0


def cohen_kappa(a: list, b: list) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length non-empty label lists")
    n = len(a)
    labels = set(a) | set(b)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}

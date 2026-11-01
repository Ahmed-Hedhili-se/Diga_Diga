"""Read-only tools the planning agent may call. Fixed allowlist; each returns ONLY counts, enums and system ids.

Nothing a stranger wrote (CV text, candidate names, email bodies, subjects, approval titles) is ever returned, so
nothing a stranger wrote can reach the model's prompt or the plan.
"""
from __future__ import annotations

from typing import Callable

from ..auth.permissions import ROLE_PERMISSIONS, Permission as P
from ..contracts import UserOut
from ..workflow import approvals, email_gate, followups

SILENT_DAYS = 3


def approvals_summary(user: UserOut) -> dict:
    q = approvals.queue(user, "pending")
    by_kind: dict[str, int] = {}
    routine = 0
    for b in q["batches"]:
        for it in b["items"]:
            routine += 1
            by_kind[it.kind.value] = by_kind.get(it.kind.value, 0) + 1
    for it in q["high_risk"]:
        by_kind[it.kind.value] = by_kind.get(it.kind.value, 0) + 1
    return {"routine": routine, "high_risk": len(q["high_risk"]), "by_kind": by_kind}


def inbox_summary(user: UserOut) -> dict:
    lanes = email_gate.digest()["lanes"]
    out = {"routine": 0, "needs_human": 0, "suspicious": 0, "urgent_needs_human": 0}
    for lane, groups in lanes.items():
        for g in groups:
            out[lane] += g["count"]
            if lane == "needs_human" and g["urgency"] == "high":
                out["urgent_needs_human"] += g["count"]
    return out


def silent_candidates(user: UserOut) -> dict:
    rows = followups.preview(SILENT_DAYS)
    return {"count": len(rows), "days": SILENT_DAYS,
            "max_days_silent": max((r["days_silent"] for r in rows), default=0)}


# name -> (function, permission needed to use it)
REGISTRY: dict[str, tuple[Callable[[UserOut], dict], P]] = {
    "approvals": (approvals_summary, P.approvals_decide),
    "inbox": (inbox_summary, P.inbox_read),
    "silent_candidates": (silent_candidates, P.followups_manage),
}


def allowed_tools(user: UserOut) -> list[str]:
    have = ROLE_PERMISSIONS.get(user.role, frozenset())
    return [name for name, (_, perm) in REGISTRY.items() if perm in have]


def call(name: str, user: UserOut) -> dict:
    if name not in allowed_tools(user):
        raise PermissionError(name)
    return REGISTRY[name][0](user)

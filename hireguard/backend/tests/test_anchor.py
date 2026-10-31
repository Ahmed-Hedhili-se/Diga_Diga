"""T5: audit chain verification and external anchoring, offline and with the network flag."""
import json

import pytest

from app import db as app_db
from app.contracts import Role
from app.workflow import anchor, audit

from test_workflow import client_for, db, make_user  # noqa: F401


@pytest.fixture
def anchors(db, monkeypatch):
    monkeypatch.setattr(anchor, "ANCHOR_DIR", db / "anchors")
    monkeypatch.delenv("HG_ANCHOR_NETWORK", raising=False)
    return db / "anchors"


def _fill(n=4):
    for i in range(n):
        audit.append("u1", "test.action", "thing", f"T{i}", {"i": i})


def _raw():
    conn = app_db.connect()
    for t in ("audit_log_no_update", "audit_log_no_delete"):
        conn.execute(f"DROP TRIGGER {t}")  # an attacker with file access
    return conn


# ---------------------------------------------------------------- endpoints, offline


def test_anchor_endpoint_offline_then_verify(anchors):
    admin, hrm, rec = make_user(Role.admin, "adm1"), make_user(Role.hr_manager, "hrm1"), make_user(Role.recruiter, "rec1")
    _fill()
    assert client_for(hrm).post("/api/audit/anchor").status_code == 403   # admin only
    r = client_for(admin).post("/api/audit/anchor")
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["method"] == "file"
    f = json.loads((anchors / r.json()["file"]).read_text())
    assert f["head_hash"] == r.json()["head_hash"] and f["seq"] == r.json()["seq"]

    assert client_for(rec).get("/api/audit/verify").status_code == 403
    v = client_for(hrm).get("/api/audit/verify").json()
    assert v["ok"] is True and v["broken_at"] is None and v["last_anchor"]["head_hash"] == r.json()["head_hash"]


def test_offline_anchor_makes_no_external_call(anchors, monkeypatch):
    calls = []
    monkeypatch.setattr(anchor, "_run", lambda cmd: calls.append(cmd) or True)
    monkeypatch.setattr(anchor.shutil, "which", lambda name: calls.append(name) or "/bin/" + name)
    _fill(1)
    assert anchor.anchor_now()["status"] == "pending"
    assert calls == []  # no ots, no git, no network unless HG_ANCHOR_NETWORK=1


# ---------------------------------------------------------------- tamper detection


def test_tampered_row_breaks_at_that_row(anchors):
    _fill()
    conn = _raw()
    conn.execute("UPDATE audit_log SET actor = 'mallory' WHERE seq = 3")
    conn.close()
    v = audit.verify()
    assert v["ok"] is False and v["broken_at"] == 3


def test_deleted_row_is_detected(anchors):
    _fill()
    conn = _raw()
    conn.execute("DELETE FROM audit_log WHERE seq = 2")
    conn.close()
    v = audit.verify()
    assert v["ok"] is False and v["broken_at"] == 3  # the first row that no longer follows its predecessor


def test_full_rewrite_after_an_anchor_is_caught_by_the_anchor(anchors):
    """Someone recomputes every hash so the chain is self-consistent: only the anchor still disagrees."""
    _fill()
    a = anchor.anchor_now()
    assert audit.verify()["ok"]
    conn = _raw()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    conn.execute("PRAGMA foreign_keys = OFF")
    prev = audit.GENESIS
    for r in rows:
        details = {"i": 99} if r["seq"] == 2 else json.loads(r["details"])
        body = audit._body(r["seq"], r["ts"], r["actor"], r["action"], r["object_type"], r["object_id"], details)
        h = audit._entry_hash(prev, body)
        conn.execute("UPDATE audit_log SET details=?, prev_hash=?, hash=? WHERE seq=?",
                     (json.dumps(details, sort_keys=True, separators=(",", ":")), prev, h, r["seq"]))
        prev = h
    conn.close()
    v = audit.verify()
    assert v["ok"] is False and v["broken_at"] == a["seq"]


def test_truncation_after_an_anchor_is_detected(anchors):
    _fill()
    a = anchor.anchor_now()
    conn = _raw()
    conn.execute("DELETE FROM audit_log WHERE seq >= ?", (a["seq"],))
    conn.close()
    v = audit.verify()
    assert v["ok"] is False and v["broken_at"] == a["seq"]


def test_untouched_history_before_a_later_anchor_still_verifies(anchors):
    _fill(2)
    anchor.anchor_now()
    _fill(2)
    anchor.anchor_now()
    assert audit.verify()["ok"] and audit.verify()["length"] >= 6


# ---------------------------------------------------------------- network mode


def _network(monkeypatch, have=(), ok=()):
    ran = []
    monkeypatch.setenv("HG_ANCHOR_NETWORK", "1")
    monkeypatch.setattr(anchor.shutil, "which", lambda name: "/bin/" + name if name in have else None)
    monkeypatch.setattr(anchor, "_run", lambda cmd: ran.append(cmd[:2]) or cmd[0] in ok or tuple(cmd[:2]) in ok)
    return ran


def test_network_mode_without_tools_stays_pending(anchors, monkeypatch):
    ran = _network(monkeypatch)
    _fill(1)
    a = anchor.anchor_now()
    assert a["status"] == "pending" and a["method"] == "file" and ran == []


def test_network_mode_with_ots_and_own_repo_pushes(anchors, monkeypatch):
    anchors.mkdir()
    (anchors / ".git").mkdir()  # data/anchors is its own repo
    ran = _network(monkeypatch, have=("ots", "git"), ok=("ots", "git"))
    _fill(1)
    a = anchor.anchor_now()
    assert a["method"] == "file+ots+git" and a["status"] == "anchored"
    assert ["ots", "stamp"] in ran and ["git", "push"] in ran


def test_git_is_never_run_unless_anchors_is_its_own_repo(anchors, monkeypatch):
    """Otherwise `git commit` would act on the surrounding HireGuard repo and commit whatever is staged."""
    ran = _network(monkeypatch, have=("ots", "git"), ok=("ots", "git"))
    _fill(1)
    a = anchor.anchor_now()
    assert a["method"] == "file+ots" and not any(c[0] == "git" for c in ran)


def test_failed_push_is_not_reported_as_anchored(anchors, monkeypatch):
    anchors.mkdir()
    (anchors / ".git").mkdir()
    _network(monkeypatch, have=("git",), ok=(("git", "add"), ("git", "commit")))
    _fill(1)
    a = anchor.anchor_now()
    assert a["status"] == "pending" and a["method"] == "file+git"


def test_anchor_does_not_hold_the_db_lock_during_network_calls(anchors, monkeypatch):
    """A slow `git push` must not block approvals: nothing is written until the network work is done."""
    anchors.mkdir()
    (anchors / ".git").mkdir()
    seen = {}

    def fake_run(cmd):
        conn = app_db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")  # would raise 'database is locked' if anchor held a write tx
            conn.execute("ROLLBACK")
            seen["free"] = True
        finally:
            conn.close()
        return True

    monkeypatch.setenv("HG_ANCHOR_NETWORK", "1")
    monkeypatch.setattr(anchor.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(anchor, "_run", fake_run)
    _fill(1)
    anchor.anchor_now()
    assert seen.get("free") is True

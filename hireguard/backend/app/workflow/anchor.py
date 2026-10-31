"""External anchoring of the audit chain head (every 30 min).

Always writes data/anchors/anchor-<seq>.json. With HG_ANCHOR_NETWORK=1 it also runs `ots stamp`
(OpenTimestamps) and, if data/anchors is inside a git repo with a remote, commits and pushes it.
No network calls otherwise. Without network the anchor is recorded with status "pending".
"""
import json
import logging
import os
import shutil
import subprocess
import threading

from ..config import DATA_DIR
from ..db import tx
from . import audit
from .common import now_iso

log = logging.getLogger("hireguard.anchor")
ANCHOR_DIR = DATA_DIR / "anchors"
INTERVAL_MIN = int(os.getenv("HG_ANCHOR_INTERVAL_MIN", "30"))


def _run(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, cwd=ANCHOR_DIR, capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def anchor_now() -> dict:
    with tx() as conn:
        seq, head_hash = audit.head(conn)
        ANCHOR_DIR.mkdir(parents=True, exist_ok=True)
        path = ANCHOR_DIR / f"anchor-{seq:08d}.json"
        path.write_text(json.dumps({"seq": seq, "head_hash": head_hash, "ts": now_iso()}, indent=2), encoding="utf-8")

        method, status = "file", "pending"
        if os.getenv("HG_ANCHOR_NETWORK", "0") == "1":
            if shutil.which("ots") and _run(["ots", "stamp", path.name]):
                method, status = "file+ots", "anchored"
            if shutil.which("git") and _run(["git", "add", "."]) and _run(["git", "commit", "-m", f"audit anchor {seq}"]):
                method += "+git"
                status = "anchored" if _run(["git", "push"]) else status
        if status == "pending":
            log.info("anchor pending: seq=%s head=%s (no network anchoring)", seq, head_hash[:12])

        conn.execute("INSERT INTO audit_anchors (ts, seq, head_hash, method, status) VALUES (?,?,?,?,?)",
                     (now_iso(), seq, head_hash, method, status))
        audit.append("system", "audit.anchor", "audit_log", str(seq),
                     {"head_hash": head_hash, "method": method, "status": status}, conn=conn)
    return {"seq": seq, "head_hash": head_hash, "method": method, "status": status, "file": path.name}


_started = False


def start_loop():
    """Daemon thread, started once from the router's startup hook. Disable with HG_ANCHOR_LOOP=0."""
    global _started
    if _started or os.getenv("HG_ANCHOR_LOOP", "1") != "1":
        return
    _started = True
    stop = threading.Event()

    def loop():
        while not stop.wait(INTERVAL_MIN * 60):
            try:
                anchor_now()
            except Exception:  # never kill the API because anchoring failed
                log.exception("anchor failed")

    threading.Thread(target=loop, name="audit-anchor", daemon=True).start()

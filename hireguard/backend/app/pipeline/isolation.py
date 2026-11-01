"""Run untrusted-PDF parsing in a separate process, with a deadline.

MuPDF is a C library. A hostile PDF can make it loop, balloon in memory or crash, and in-process that takes the
whole API down (or worse). With isolation on, parsing runs in a pool of worker processes:
  - a call that exceeds the deadline is killed, and the pool is rebuilt;
  - a worker that crashes (segfault, out of memory) breaks only that request;
  - on POSIX each worker also gets an address-space limit.
The API process never opens the PDF. Off by default in development (spawning costs about a second), on in
production (HG_ENV=production turns it on, and hardening.py refuses to start with it switched off).
"""
from __future__ import annotations

import logging
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool

from .. import config

log = logging.getLogger("hireguard.isolation")


class IsolationError(Exception):
    """The parse took too long or its worker died. The upload is rejected; nothing else is affected."""


_pool: ProcessPoolExecutor | None = None
_lock = threading.Lock()


def _init_worker(memory_mb: int) -> None:
    try:
        import resource  # POSIX only: no-op on Windows
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:  # noqa: BLE001 - best effort: the deadline and crash containment still apply
        pass


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=config.PARSE_WORKERS, mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_init_worker, initargs=(config.PARSE_MEMORY_MB,),
                                        max_tasks_per_child=100)
        return _pool


def _discard_pool(pool: ProcessPoolExecutor) -> None:
    """Kill every worker (shutdown() alone would wait for a stuck one) and let the next call build a fresh pool."""
    global _pool
    with _lock:
        if _pool is pool:
            _pool = None
    for proc in list(getattr(pool, "_processes", {}).values()):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
    pool.shutdown(wait=False, cancel_futures=True)


def run_isolated(fn, *args, timeout: float | None = None, **kwargs):
    """fn(*args, **kwargs), in a worker process when isolation is on. `fn` must be importable (module level)."""
    if not config.PARSE_ISOLATION:
        return fn(*args, **kwargs)
    pool = _get_pool()
    try:
        return pool.submit(fn, *args, **kwargs).result(timeout=timeout or config.PARSE_TIMEOUT_S)
    except FutureTimeout:
        log.warning("isolated parse exceeded %.0f s: workers killed", timeout or config.PARSE_TIMEOUT_S)
        _discard_pool(pool)
        raise IsolationError("analysis took too long") from None
    except BrokenProcessPool:
        log.warning("isolated parse worker died: pool rebuilt")
        _discard_pool(pool)
        raise IsolationError("analysis failed") from None

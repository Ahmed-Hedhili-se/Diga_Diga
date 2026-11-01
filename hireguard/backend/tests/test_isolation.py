"""PDF parsing in a worker process: a deadline, crash containment, and the same answers as in-process."""
import os
import time

import pytest

from app import config
from app.pipeline import isolation, service
from app.pipeline.isolation import IsolationError, run_isolated


@pytest.fixture()
def on(monkeypatch):
    monkeypatch.setattr(config, "PARSE_ISOLATION", True)
    monkeypatch.setattr(config, "PARSE_TIMEOUT_S", 3.0)
    yield
    pool = isolation._pool
    if pool is not None:
        isolation._discard_pool(pool)


def test_off_runs_in_process(monkeypatch):
    monkeypatch.setattr(config, "PARSE_ISOLATION", False)
    assert run_isolated(os.getpid) == os.getpid()


def test_on_runs_in_another_process(on):
    assert run_isolated(os.getpid) != os.getpid()


def test_a_stuck_parse_is_killed_at_the_deadline_and_the_pool_recovers(on):
    t0 = time.monotonic()
    with pytest.raises(IsolationError, match="too long"):
        run_isolated(time.sleep, 60, timeout=1.0)
    assert time.monotonic() - t0 < 10                      # not 60 s
    assert run_isolated(os.getpid) != os.getpid()          # a fresh pool serves the next upload


def test_a_crashing_worker_breaks_only_that_request(on):
    with pytest.raises(IsolationError, match="failed"):
        run_isolated(os._exit, 1)
    assert run_isolated(os.getpid) != os.getpid()


def test_the_same_pdf_gets_the_same_verdict_in_and_out_of_isolation(on, monkeypatch):
    from pathlib import Path
    pdf = next(iter(sorted((Path(config.ROOT) / "data" / "test_pdfs").glob("*.pdf")))).read_bytes()
    isolated = service.check_upload(pdf)
    monkeypatch.setattr(config, "PARSE_ISOLATION", False)
    assert service.check_upload(pdf) == isolated


def test_rejections_from_the_worker_keep_their_message(on):
    with pytest.raises(service.UploadRejected, match="unreadable PDF"):
        service.check_upload(b"%PDF-1.4 this is not a pdf at all")


def test_the_sanitizer_result_crosses_the_process_boundary_unchanged(on, monkeypatch):
    from pathlib import Path
    from app.pipeline.sanitizer import sanitize
    pdf = (Path(config.ROOT) / "data" / "test_pdfs" / "annotation_metadata.pdf").read_bytes()
    inside = run_isolated(sanitize, pdf, doc_id="DOC")
    monkeypatch.setattr(config, "PARSE_ISOLATION", False)
    assert inside == sanitize(pdf, doc_id="DOC")
    assert inside.hidden_findings                           # the hidden-content findings survive the pickle

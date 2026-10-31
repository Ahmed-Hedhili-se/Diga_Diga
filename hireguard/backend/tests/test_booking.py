"""T2: one interview per candidate request. Executing a booking withdraws its sibling slot proposals."""
import pytest

from app import db as app_db
from app.contracts import EmailIntent, Role
from app.workflow import approvals, audit, drafting, mock_calendar

from test_workflow import client_for, db, make_user  # noqa: F401

CAND = {"candidate_id": "CAND-003", "email": "sarah.haddad@gmail.example", "name": "Sarah Haddad",
        "job_id": "JOB-DATA-01", "status": None}


def _three_slots(inbox_id="EML-003", cand=CAND):
    with app_db.tx() as conn:
        items = drafting.draft_reply(conn, inbox_id, cand, EmailIntent.interview_availability, "en")
    assert len(items) == 3
    return items


def _count(table):
    conn = app_db.connect()
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n


def test_executing_one_slot_withdraws_siblings(db):
    hrm = make_user(Role.hr_manager, "hrm1")
    a, b, c3 = _three_slots()
    c = client_for(hrm)
    for item in (a, b):
        assert c.post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"}).status_code == 200

    assert c.post(f"/api/executor/run/{a.id}").status_code == 200
    # B was approved but its sibling got booked first: withdrawn, never executable
    assert approvals.get_item(b.id).status == "rejected"
    assert approvals.get_item(c3.id).status == "rejected"
    assert c.post(f"/api/executor/run/{b.id}").status_code == 403
    assert _count("interviews") == 1 and _count("email_outbox") == 1

    entries = audit.list_entries(50)
    withdrawn = [e for e in entries if e.action == "approval.withdraw"]
    assert {e.object_id for e in withdrawn} == {b.id, c3.id}
    assert all(e.details["reason"] == "sibling_booked" and e.details["booked_item"] == a.id for e in withdrawn)
    assert any(e.action == "executor.refused" and e.object_id == b.id for e in entries)
    assert audit.verify()["ok"]


def test_withdrawn_sibling_cannot_be_approved_later(db):
    hrm = make_user(Role.hr_manager, "hrm1")
    a, b, _ = _three_slots()
    c = client_for(hrm)
    c.post(f"/api/approvals/{a.id}/decision", json={"decision": "approve"})
    c.post(f"/api/executor/run/{a.id}")
    assert c.post(f"/api/approvals/{b.id}/decision", json={"decision": "approve"}).status_code == 409


def test_other_candidates_and_requests_are_untouched(db):
    hrm = make_user(Role.hr_manager, "hrm1")
    a, _, _ = _three_slots()
    other = dict(CAND, candidate_id="CAND-004", email="k@gmail.example", name="Karim")
    o1, *_ = _three_slots("EML-004", other)
    again, *_ = _three_slots("EML-003B")  # same candidate, a different inbox message
    c = client_for(hrm)
    c.post(f"/api/approvals/{a.id}/decision", json={"decision": "approve"})
    c.post(f"/api/executor/run/{a.id}")
    assert approvals.get_item(o1.id).status == "pending"
    assert approvals.get_item(again.id).status == "pending"


def test_calendar_refuses_an_already_booked_slot(db):
    hrm = make_user(Role.hr_manager, "hrm1")
    a, *_ = _three_slots()
    # a different candidate whose proposal points at the same slot
    other = dict(CAND, candidate_id="CAND-004", email="k@gmail.example", name="Karim")
    with app_db.tx() as conn:
        clash = approvals.create_item("interview_booking", "clash", a.payload | {"candidate_id": "CAND-004",
                                      "inbox_id": "EML-004"}, "system", conn=conn)
    c = client_for(hrm)
    for item in (a, clash):
        c.post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"})
    assert c.post(f"/api/executor/run/{a.id}").status_code == 200
    r = c.post(f"/api/executor/run/{clash.id}")
    assert r.status_code == 409 and _count("interviews") == 1
    assert approvals.get_item(clash.id).status == "approved"  # rolled back: nothing half-done
    _ = other


def test_slot_booked_twice_inside_one_request_is_impossible(db):
    with app_db.tx() as conn:
        free = mock_calendar.free_slots("recruiter", 1, conn=conn)[0]
        mock_calendar.book(conn, free["id"], "CAND-001")
        with pytest.raises(Exception) as e:
            mock_calendar.book(conn, free["id"], "CAND-002")
        assert e.value.status_code == 409

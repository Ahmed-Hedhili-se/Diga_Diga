"""The ROI calculator: pure arithmetic, labelled inputs, validated ranges, restricted to HR managers and admins."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.auth.core import SESSION_COOKIE, create_session, hash_password
from app.scoring import money, routes

PROFILES = {  # docs/business.md, section 3
    "small": ({"roles_per_year": 5, "cvs_per_role": 100, "plan_price_tnd_per_month": 150},
              dict(screening=473, faster=4500, total=4973, price=1800, ratio=2.8, screening_only=0.3)),
    "mid": ({"roles_per_year": 20, "cvs_per_role": 150, "plan_price_tnd_per_month": 400},
            dict(screening=2840, faster=18000, total=20840, price=4800, ratio=4.3, screening_only=0.6)),
    "large": ({"roles_per_year": 60, "cvs_per_role": 200, "plan_price_tnd_per_month": 1000},
              dict(screening=11360, faster=54000, total=65360, price=12000, ratio=5.4, screening_only=0.9)),
}


@pytest.mark.parametrize("name", list(PROFILES))
def test_the_business_document_rows_are_reproduced(name):
    entered, want = PROFILES[name]
    o = money.roi(entered)["outputs"]
    assert o["screening_value_tnd"] == want["screening"]
    assert o["faster_hiring_value_tnd"] == want["faster"]
    assert o["total_value_tnd"] == want["total"]
    assert o["plan_price_tnd_per_year"] == want["price"]
    assert o["total_value_over_price"] == want["ratio"]
    assert o["screening_only_over_price"] == want["screening_only"]


def test_it_is_deterministic_and_changes_nothing_else():
    a, b = money.roi({"roles_per_year": 7}), money.roi({"roles_per_year": 7})
    assert a == b
    assert money.MINUTES_PER_UNIT == {"cv_screening": 6.0, "emails": 4.0, "documents": 10.0, "answers": 5.0}


def test_every_input_says_whether_it_is_an_assumption_or_typed():
    r = money.roi({"roles_per_year": 12})["inputs"]
    assert r["roles_per_year"] == {"value": 12, "status": "entered", "source_id": None}
    assert r["minutes_per_cv"]["status"] == "assumption"
    assert r["recruiter_cost_tnd_per_hour"] == {"value": 14.2, "status": "assumption", "source_id": "E10"}
    assert {v["status"] for v in money.roi()["inputs"].values()} == {"assumption"}


def test_a_free_plan_has_no_ratio_instead_of_a_division_by_zero():
    o = money.roi({"plan_price_tnd_per_month": 0})["outputs"]
    assert o["total_value_over_price"] is None and o["screening_only_over_price"] is None


def test_the_smallest_allowed_inputs_still_give_a_positive_payback():
    o = money.roi({"minutes_per_cv": 0.5, "days_saved_per_role": 0, "vacancy_cost_tnd_per_day": 0,
                   "recruiter_cost_tnd_per_hour": 1})["outputs"]
    assert o["payback_months"] is not None and o["payback_months"] > 0       # tiny but positive value: never a division by zero


@pytest.mark.parametrize("bad", [{"roles_per_year": -1}, {"cvs_per_role": 10**9}, {"minutes_per_cv": 0},
                                 {"recruiter_cost_tnd_per_hour": -5}, {"plan_price_tnd_per_month": 10**7}])
def test_out_of_range_values_are_refused(bad):
    with pytest.raises(ValueError):
        money.roi(bad)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = db.connect()
    for uid, role in (("u-rec", "recruiter"), ("u-hrm", "hr_manager"), ("u-adm", "admin"), ("u-emp", "employee")):
        conn.execute("INSERT INTO auth_users (id, email, display_name, role, pw_hash) VALUES (?,?,?,?,?)",
                     (uid, f"{uid}@t", uid, role, hash_password("x" * 12)))
    conn.close()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    return TestClient(app)


def login(client, uid):
    token, csrf = create_session(uid)
    client.cookies.set(SESSION_COOKIE, token)


def test_only_hr_managers_and_admins_can_read_it(client):
    assert client.get("/api/money/roi").status_code == 401
    for uid, code in (("u-emp", 403), ("u-rec", 403), ("u-hrm", 200), ("u-adm", 200)):
        login(client, uid)
        assert client.get("/api/money/roi").status_code == code, uid


def test_the_route_returns_the_labelled_inputs_and_outputs(client):
    login(client, "u-hrm")
    r = client.get("/api/money/roi?roles_per_year=5&cvs_per_role=100&plan_price_tnd_per_month=150").json()
    assert r["outputs"]["total_value_tnd"] == 4973
    assert r["inputs"]["roles_per_year"]["status"] == "entered"
    assert r["inputs"]["minutes_per_cv"]["status"] == "assumption"
    assert "Hypothesis" in r["note"]


@pytest.mark.parametrize("q", ["roles_per_year=-1", "cvs_per_role=1000000000", "minutes_per_cv=0", "plan_price_tnd_per_month=-1",
                               "roles_per_year=abc"])
def test_the_route_answers_422_for_bad_values(client, q):
    login(client, "u-hrm")
    assert client.get(f"/api/money/roi?{q}").status_code == 422

"""Demo seeding (P4 demo lead). Run: python -m app.seed

Creates the 5 demo users with random passwords printed ONCE (no default accounts),
then asks each layer to seed its own demo data.
"""
import importlib
import secrets
import sys

from .contracts import Role
from .db import connect, init_db

# Import modules so their schemas register before init_db()
from .auth import routes as _auth  # noqa: F401
from .auth.routes import create_user

DEMO_USERS = [
    ("recruiter@hireguard.demo", "Amira Ben Salah (Recruiter)", Role.recruiter),
    ("hrm@hireguard.demo", "Karim Trabelsi (HR Manager)", Role.hr_manager),
    ("hrm2@hireguard.demo", "Leila Mansour (HR Manager, 2nd approver)", Role.hr_manager),
    ("employee@hireguard.demo", "Youssef Gharbi (Employee EMP-001)", Role.employee),
    ("admin@hireguard.demo", "Sami Jaziri (Admin)", Role.admin),
]

LAYER_SEEDS = [
    ("app.workflow.demo", "seed_employees", "P3 employee records"),
    ("app.scoring.jobs", "seed_jobs", "P2 jobs/rubrics"),
    ("app.pipeline.demo", "seed_candidates", "P1 candidates"),  # before inbox: gate matches senders to candidates
    ("app.workflow.demo", "seed_inbox", "P3 inbox/approvals"),
    ("app.workflow.demo", "seed_followup_demo", "P3 follow-up demo: one candidate silent for 5 days (backdated, audited)"),
    ("app.scoring.offer_fit", "seed_conditions", "Fast-track declared conditions (fictional)"),
    ("app.scoring.rediscover", "seed_pool", "Fast-track talent pool: 20 fictional past applicants"),
    ("app.scoring.rediscover", "seed_other_roles", "Applicants for the two other open roles (fictional)"),
    ("app.team.knowledge_gaps", "seed_log", "HR Nexus: fictional answer-desk log (no question text)"),
]


def _import_all_layers():
    for mod in ("app.pipeline.routes", "app.scoring.routes", "app.workflow.routes", "app.team.routes"):
        try:
            importlib.import_module(mod)
        except ImportError as e:
            print(f"  [skip] {mod} not importable yet: {e}")


def seed_users() -> list[tuple[str, str, str]]:
    created = []
    conn = connect()
    try:
        existing = {r["email"] for r in conn.execute("SELECT email FROM auth_users")}
    finally:
        conn.close()
    for email, name, role in DEMO_USERS:
        if email in existing:
            continue
        pw = secrets.token_urlsafe(12)
        create_user(email, name, role, pw)
        created.append((email, role.value, pw))
    return created


def main():
    _import_all_layers()
    init_db()

    created = seed_users()
    if created:
        print("\n=== Demo accounts (passwords shown ONCE, store them now) ===")
        for email, role, pw in created:
            print(f"  {role:<11} {email:<28} {pw}")
        print()
    else:
        print("Demo users already exist (passwords are not recoverable; reset the DB to regenerate).")

    for mod, fn, label in LAYER_SEEDS:
        try:
            getattr(importlib.import_module(mod), fn)()
            print(f"  [ok]   {label}")
        except (ImportError, AttributeError) as e:
            print(f"  [skip] {label}: {mod}.{fn}() not available yet ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()

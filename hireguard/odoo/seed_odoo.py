"""Seed a local Odoo 17 for the HireGuard demo. FICTIONAL DATA ONLY. Stdlib only, safe to re-run.

    python odoo/seed_odoo.py [--url http://localhost:8069] [--db hireguard] [--admin admin] [--password admin]
                             [--max-cvs 10]

As admin it:
  1. creates/updates the bot user (Internal User + Recruitment / Officer only) with a fresh random password;
  2. creates the stage "Shortlisted (HireGuard)";
  3. creates one hr.job per HireGuard job (same titles as backend/app/scoring/jobs.py);
  4. creates applicants with their PDF CV attached: generated CVs from data/cv_ground_truth/pdf/
     (`python eval/gen_cvs.py --pdf`) and the poisoned test PDFs from data/test_pdfs/ on JOB-DATA-01;
  5. books two busy events for the bot on the next business day (they block interview slots);
  6. prints the HG_ODOO_* lines to paste into .env.
"""
from __future__ import annotations

import argparse
import ast
import base64
import json
import secrets
import sys
import xmlrpc.client
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS_PY = ROOT / "backend" / "app" / "scoring" / "jobs.py"
GT_DIR = ROOT / "data" / "cv_ground_truth"
TEST_PDFS = ROOT / "data" / "test_pdfs"

BOT_LOGIN = "hireguard-bot@example.tn"
SHORTLIST_STAGE = "Shortlisted (HireGuard)"
POISONED_JOB = "JOB-DATA-01"
# fictional people for the poisoned test CVs
POISONED_NAMES = ["Nour Ben Amor", "Hichem Dridi", "Rania Chaabane", "Walid Ferchichi", "Salma Bouazizi",
                  "Anis Khemiri", "Mariem Toumi", "Bilel Saidi", "Asma Riahi", "Oussama Hamdi"]
TUNIS = timezone(timedelta(hours=1))
ODOO_DT = "%Y-%m-%d %H:%M:%S"


def load_jobs() -> dict[str, dict]:
    """JOBS literal from the backend, without importing the app (no third-party deps needed here)."""
    tree = ast.parse(JOBS_PY.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "JOBS":
            return ast.literal_eval(node.value)
    sys.exit(f"JOBS not found in {JOBS_PY}")


class Odoo:
    def __init__(self, url: str, db: str, login: str, password: str):
        self.db, self.password = db, password
        self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, login, password, {})
        if not self.uid:
            sys.exit(f"login failed for {login} on {db} at {url}")
        self.obj = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def __call__(self, model: str, method: str, *args, **kwargs):
        return self.obj.execute_kw(self.db, self.uid, self.password, model, method, list(args), kwargs)

    def has_field(self, model: str, field: str) -> bool:
        """Field names moved between Odoo versions (e.g. res.users.groups_id -> group_ids in 19+)."""
        cache = self.__dict__.setdefault("_fields", {})
        if model not in cache:
            cache[model] = set(self(model, "fields_get", attributes=["type"]))
        return field in cache[model]

    def find(self, model: str, domain: list) -> int | None:
        ids = self(model, "search", domain, limit=1)
        return ids[0] if ids else None

    def ensure(self, model: str, domain: list, vals: dict) -> int:
        return self.find(model, domain) or self(model, "create", vals)

    def xmlid(self, module: str, name: str) -> int:
        rows = self("ir.model.data", "search_read", [("module", "=", module), ("name", "=", name)], fields=["res_id"])
        if not rows:
            sys.exit(f"missing {module}.{name}: is hr_recruitment installed?")
        return rows[0]["res_id"]


def seed_bot(odoo: Odoo) -> tuple[int, str]:
    groups = [odoo.xmlid("base", "group_user"), odoo.xmlid("hr_recruitment", "group_hr_recruitment_user")]
    password = secrets.token_urlsafe(18)
    groups_field = "groups_id" if odoo.has_field("res.users", "groups_id") else "group_ids"
    vals = {"name": "HireGuard bot", "login": BOT_LOGIN, "email": BOT_LOGIN, "password": password,
            groups_field: [(6, 0, groups)]}
    uid = odoo.find("res.users", [("login", "=", BOT_LOGIN)])
    if uid:
        odoo("res.users", "write", [uid], vals)
    else:
        uid = odoo("res.users", "create", vals)
    return uid, password


def add_applicant(odoo: Odoo, job_id: int, job_title: str, name: str, email: str, pdf: Path) -> bool:
    on_applicant = [("res_model", "=", "hr.applicant"), ("mimetype", "=", "application/pdf")]
    applicant = odoo.find("hr.applicant", [("email_from", "=", email), ("job_id", "=", job_id)])
    if applicant:
        if odoo.find("ir.attachment", on_applicant + [("res_id", "=", applicant), ("file_size", ">", 0)]):
            return False
        # An earlier run on Odoo 19+ wrote `datas`, which no longer exists: the CV was stored empty. Replace it.
        empty = odoo("ir.attachment", "search", on_applicant + [("res_id", "=", applicant)])
        if empty:
            odoo("ir.attachment", "unlink", empty)
        created = False
    else:
        partner = odoo.ensure("res.partner", [("email", "=", email)], {"name": name, "email": email})
        vals = {"partner_id": partner, "partner_name": name, "email_from": email, "job_id": job_id}
        if odoo.has_field("hr.applicant", "name"):  # the subject field was dropped in recent Odoo versions
            vals["name"] = f"{job_title} - {name}"
        applicant = odoo("hr.applicant", "create", vals)
        created = True
    content = "datas" if odoo.has_field("ir.attachment", "datas") else "raw"  # both take base64 text over RPC
    odoo("ir.attachment", "create", {"name": pdf.name, "res_model": "hr.applicant", "res_id": applicant,
                                     "mimetype": "application/pdf",
                                     content: base64.b64encode(pdf.read_bytes()).decode()})
    return created


def seed_applicants(odoo: Odoo, jobs: dict[str, dict], job_ids: dict[str, int], max_cvs: int) -> int:
    created = 0
    pdfs = sorted((GT_DIR / "pdf").glob("*.pdf"))[:max_cvs] if (GT_DIR / "pdf").is_dir() else []
    if not pdfs:
        print("  no generated CVs found: run `python eval/gen_cvs.py --pdf` to add some (poisoned CVs still seeded)")
    for pdf in pdfs:
        spec = GT_DIR / f"{pdf.stem}.json"
        if not spec.exists():
            continue
        gt = json.loads(spec.read_text(encoding="utf-8"))["ground_truth"]
        if gt["job_id"] in job_ids:
            created += add_applicant(odoo, job_ids[gt["job_id"]], jobs[gt["job_id"]]["title"], gt["name"],
                                     gt["email"], pdf)
    poisoned = [p for p in sorted(TEST_PDFS.glob("*.pdf")) if p.name != "clean.pdf"]
    for i, pdf in enumerate(poisoned):
        name = POISONED_NAMES[i % len(POISONED_NAMES)]
        email = f"{name.lower().replace(' ', '.')}.{pdf.stem.replace('_', '-')}@example.tn"
        created += add_applicant(odoo, job_ids[POISONED_JOB], jobs[POISONED_JOB]["title"], name, email, pdf)
    return created


def seed_busy_events(odoo: Odoo, bot_uid: int) -> int:
    partner = odoo("res.users", "read", [bot_uid], fields=["partner_id"])[0]["partner_id"][0]
    day = date.today() + timedelta(days=1)
    while day.weekday() >= 5:  # interview slots are on business days
        day += timedelta(days=1)
    created = 0
    for hour in (10, 14):
        start = datetime(day.year, day.month, day.day, hour, tzinfo=TUNIS).astimezone(timezone.utc)
        vals = {"name": "Busy (seed)", "start": start.strftime(ODOO_DT),
                "stop": (start + timedelta(hours=1)).strftime(ODOO_DT), "user_id": bot_uid,
                "partner_ids": [(6, 0, [partner])]}
        if not odoo.find("calendar.event", [("name", "=", vals["name"]), ("start", "=", vals["start"])]):
            odoo("calendar.event", "create", vals)
            created += 1
    return created


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:8069")
    ap.add_argument("--db", default="hireguard")
    ap.add_argument("--admin", default="admin")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--max-cvs", type=int, default=10)
    args = ap.parse_args()
    url = args.url.rstrip("/")

    odoo = Odoo(url, args.db, args.admin, args.password)
    jobs = load_jobs()

    bot_uid, bot_password = seed_bot(odoo)
    print(f"bot user {BOT_LOGIN} (id {bot_uid}): Internal User + Recruitment / Officer")
    odoo.ensure("hr.recruitment.stage", [("name", "=", SHORTLIST_STAGE)], {"name": SHORTLIST_STAGE, "sequence": 50})
    print(f"stage {SHORTLIST_STAGE!r} ready")
    job_ids = {jid: odoo.ensure("hr.job", [("name", "=", j["title"])], {"name": j["title"]}) for jid, j in jobs.items()}
    print(f"{len(job_ids)} jobs ready")
    print(f"{seed_applicants(odoo, jobs, job_ids, args.max_cvs)} applicants created")
    print(f"{seed_busy_events(odoo, bot_uid)} busy calendar events created")

    print("\n# paste into .env (better: log in as the bot, create an API key and use it instead of the password)")
    print("HG_ODOO_ENABLED=1")
    print(f"HG_ODOO_URL={url}")
    print(f"HG_ODOO_DB={args.db}")
    print(f"HG_ODOO_USER={BOT_LOGIN}")
    print(f"HG_ODOO_API_KEY={bot_password}")


if __name__ == "__main__":
    main()

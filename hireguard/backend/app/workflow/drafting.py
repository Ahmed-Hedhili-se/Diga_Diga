"""Reply drafting from typed fields only. Nothing in the reply comes from the incoming email body:
the template is picked from the intent enum, the language from the language enum, and the slots from our DB.
Drafts become approval items; nothing is sent here.
"""
import sqlite3

from ..contracts import ApprovalItem, ApprovalKind, EmailIntent
from . import approvals, mock_calendar, templates
from .common import table_exists

COMPANY = "HireGuard Demo SARL"
RECRUITER = {"id": "recruiter", "name": "Equipe Recrutement"}

# fallback titles for the frozen demo job IDs (P2's jobs table wins when present)
JOB_TITLES = {
    "JOB-DATA-01": "Data Engineer",
    "JOB-FS-02": "Développeur Full-stack",
    "JOB-HR-03": "Assistant(e) RH",
}

STATUS_LABELS = {
    "fr": {"received": "reçue", "under_review": "en cours d'étude", "shortlisted": "présélectionnée",
           "interview": "entretien planifié", "rejected": "non retenue", "hired": "retenue"},
    "en": {"received": "received", "under_review": "under review", "shortlisted": "shortlisted",
           "interview": "interview scheduled", "rejected": "not selected", "hired": "selected"},
    "ar": {"received": "تم الاستلام", "under_review": "قيد الدراسة", "shortlisted": "في القائمة المختصرة",
           "interview": "تم تحديد مقابلة", "rejected": "لم يتم قبولها", "hired": "تم قبولها"},
}

TEMPLATE_FOR_INTENT = {
    EmailIntent.application: "ack_application",
    EmailIntent.status_question: "status_update",
    EmailIntent.interview_availability: "interview_invite",
    EmailIntent.reschedule: "interview_invite",
}


def _lang(lang: str) -> str:
    return lang if lang in ("fr", "en", "ar") else "fr"


def job_title(conn: sqlite3.Connection, job_id: str) -> str:
    for table in ("jobs", "score_jobs"):
        if table_exists(conn, table):
            try:
                r = conn.execute(f"SELECT title FROM {table} WHERE job_id = ?", (job_id,)).fetchone()
                if r:
                    return r["title"]
            except sqlite3.OperationalError:
                pass
    return JOB_TITLES.get(job_id, job_id)


def _slot_label(slot: dict, lang: str) -> str:
    start = mock_calendar.parse(slot["start"])
    return start.strftime("%Y-%m-%d %H:%M") + (" (heure de Tunis)" if lang == "fr" else
                                               " (توقيت تونس)" if lang == "ar" else " (Tunis time)")


def draft_reply(conn: sqlite3.Connection, inbox_id: str, candidate: dict, intent: EmailIntent, lang: str,
                created_by: str = "system") -> list[ApprovalItem]:
    """`candidate` must come from the verified-sender match (email_gate), never from the email text."""
    name = TEMPLATE_FOR_INTENT.get(intent)
    if name is None:
        return []  # other intents are handled by a human
    lang = _lang(lang)
    slots = {"candidate_name": candidate["name"], "job_title": job_title(conn, candidate["job_id"]),
             "recruiter_name": RECRUITER["name"], "company_name": COMPANY}
    base = {"inbox_id": inbox_id, "candidate_id": candidate["candidate_id"], "recipient_verified": True}

    if name == "interview_invite":
        free = mock_calendar.free_slots(RECRUITER["id"], 3, conn=conn)
        if not free:
            return []
        out = []
        # HR approves exactly one of the 3 proposed slots; the others are rejected or left to expire
        for slot in free:
            subject, body = templates.render("email", name, lang, slots | {"slot_label": _slot_label(slot, lang)})
            email = {"to": candidate["email"], "subject": subject, "body": body, "lang": lang}
            out.append(approvals.create_item(
                ApprovalKind.interview_booking, f"Interview {candidate['candidate_id']} at {slot['start'][:16]}",
                base | {"slot_id": slot["id"], "slot": {"start": slot["start"], "end": slot["end"]},
                        "job_id": candidate["job_id"], "recruiter_id": RECRUITER["id"], "email": email},
                created_by, diff={"before": None, "after": {"to": candidate["email"], "slot": slot["start"]}},
                conn=conn))
        return out

    if name == "status_update":
        slots["status_label"] = STATUS_LABELS[lang].get(candidate.get("status") or "under_review",
                                                        STATUS_LABELS[lang]["under_review"])
    subject, body = templates.render("email", name, lang, slots)
    return [approvals.create_item(
        ApprovalKind.email_send, f"Reply to {candidate['candidate_id']}: {name}",
        base | {"to": candidate["email"], "subject": subject, "body": body, "lang": lang},
        created_by, diff={"before": None, "after": {"to": candidate["email"], "subject": subject}}, conn=conn)]

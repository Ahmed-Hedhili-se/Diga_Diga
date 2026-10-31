"""Personal Answer Desk questions routed to HR (P1 calls `create_employee_question`).

The question text is stored for HR to read and is NEVER fed to a model or copied into any outbound message.
Risk is computed by code from the typed topic only. HR answers by picking a template reply (enum); the reply
is an `email_send` approval item addressed to the employee's own account, so it needs a second HR approval
and the executor like every other send.
"""
import sqlite3
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, constr

from ..contracts import ApprovalItem, ApprovalKind, Role, UserOut
from ..db import connect, register_schema, tx
from . import approvals, audit, drafting, templates
from .common import new_id, now_iso, table_exists

Topic = Literal["leave", "salary", "certificate", "contract", "other"]
ReplyTemplate = Literal["received", "contact_hr", "use_documents"]
Lang = Literal["fr", "en", "ar"]

TOPIC_RISK = {"leave": 20, "certificate": 20, "salary": 40, "contract": 40, "other": 30}

TOPIC_LABELS = {
    "fr": {"leave": "congés", "salary": "salaire", "certificate": "attestation", "contract": "contrat", "other": "autre"},
    "en": {"leave": "leave", "salary": "salary", "certificate": "certificate", "contract": "contract", "other": "other"},
    "ar": {"leave": "الإجازات", "salary": "الأجر", "certificate": "الشهادات", "contract": "العقد", "other": "أخرى"},
}
REPLY_LABELS = {
    "fr": {"received": "Nous avons bien reçu votre question ; un membre de l'équipe RH vous répondra personnellement.",
           "contact_hr": "Cette question est personnelle : merci de contacter directement le service RH.",
           "use_documents": "Vous pouvez demander ce document depuis la page Documents de votre espace."},
    "en": {"received": "We have received your question; an HR team member will answer you personally.",
           "contact_hr": "This question is personal: please contact the HR office directly.",
           "use_documents": "You can request this document from the Documents page of your space."},
    "ar": {"received": "تلقينا سؤالكم وسيجيبكم أحد أعضاء فريق الموارد البشرية شخصيا.",
           "contact_hr": "هذا السؤال شخصي: يرجى الاتصال مباشرة بمصلحة الموارد البشرية.",
           "use_documents": "يمكنكم طلب هذه الوثيقة من صفحة الوثائق في فضائكم."},
}


class QuestionIn(BaseModel, extra="forbid"):
    topic: Topic
    text: constr(min_length=1, max_length=2000)


class ReplyIn(BaseModel, extra="forbid"):
    template: ReplyTemplate
    lang: Lang = "fr"


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS employee_questions (
            id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            topic TEXT NOT NULL CHECK (topic IN ('leave','salary','certificate','contract','other')),
            text TEXT NOT NULL,
            risk INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('open','reply_drafted','answered')),
            reply_item_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS employee_questions_user ON employee_questions(user_id, created_at);
        """
    )


def risk_for(topic: str) -> int:
    return TOPIC_RISK[topic]


def _public(r, with_text: bool = True) -> dict:
    d = {"id": r["id"], "topic": r["topic"], "risk": r["risk"], "status": r["status"],
         "created_at": r["created_at"], "reply_item_id": r["reply_item_id"]}
    if with_text:
        d["text"] = r["text"]
    return d


def _employee_row(conn, user_id: str):
    if not table_exists(conn, "workflow_employees"):
        return None
    return conn.execute("SELECT * FROM workflow_employees WHERE user_id = ?", (user_id,)).fetchone()


def create_employee_question(user: UserOut, topic: str, text: str) -> dict:
    """In-process entry for P1's Answer Desk. Returns a ticket without the text."""
    if topic not in TOPIC_RISK:
        raise ValueError(f"unknown topic {topic!r}")
    with tx() as conn:
        emp = _employee_row(conn, user.id)
        qid = new_id("QST")
        risk = risk_for(topic)
        conn.execute("INSERT INTO employee_questions VALUES (?,?,?,?,?,?, 'open', NULL, ?)",
                     (qid, emp["employee_id"] if emp else user.id, user.id, topic, text[:2000], risk, now_iso()))
        # the text itself is deliberately not logged
        audit.append(user.id, "question.create", "employee_question", qid,
                     {"topic": topic, "risk": risk, "length": len(text)}, conn=conn)
        r = conn.execute("SELECT * FROM employee_questions WHERE id = ?", (qid,)).fetchone()
    return _public(r, with_text=False)


def list_for(user: UserOut) -> list[dict]:
    conn = connect()
    try:
        if user.role == Role.hr_manager:
            rows = conn.execute("SELECT * FROM employee_questions "
                                "ORDER BY status = 'answered', risk DESC, created_at").fetchall()
        else:
            rows = conn.execute("SELECT * FROM employee_questions WHERE user_id = ? ORDER BY created_at DESC",
                                (user.id,)).fetchall()
    finally:
        conn.close()
    return [_public(r) for r in rows]


def get_for(user: UserOut, qid: str) -> dict:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM employee_questions WHERE id = ?", (qid,)).fetchone()
    finally:
        conn.close()
    # 404 for "not yours" too: ticket IDs can't be enumerated
    if not r or (user.role != Role.hr_manager and r["user_id"] != user.id):
        raise HTTPException(404, "question not found")
    return _public(r)


def draft_reply(user: UserOut, qid: str, template: str, lang: str = "fr") -> ApprovalItem:
    with tx() as conn:
        q = conn.execute("SELECT * FROM employee_questions WHERE id = ?", (qid,)).fetchone()
        if not q:
            raise HTTPException(404, "question not found")
        if q["status"] != "open":
            raise HTTPException(409, f"question is {q['status']}")
        # recipient: the employee's own account address from our auth table, never from the question text
        acct = conn.execute("SELECT email, display_name FROM auth_users WHERE id = ?", (q["user_id"],)).fetchone()
        if not acct:
            raise HTTPException(409, "employee account not found")
        emp = _employee_row(conn, q["user_id"])
        slots = {"employee_name": emp["full_name"] if emp else acct["display_name"],
                 "topic_label": TOPIC_LABELS[lang][q["topic"]], "reply_label": REPLY_LABELS[lang][template],
                 "recruiter_name": drafting.RECRUITER["name"], "company_name": drafting.COMPANY}
        subject, body = templates.render("email", "question_reply", lang, slots)
        item = approvals.create_item(
            ApprovalKind.email_send, f"Reply to employee question {qid} ({q['topic']})",
            {"template": "question_reply", "question_id": qid, "to": acct["email"], "recipient_verified": True,
             "subject": subject, "body": body, "lang": lang},
            created_by=user.id, risk=q["risk"],
            diff={"before": None, "after": {"to": acct["email"], "subject": subject}}, conn=conn)
        conn.execute("UPDATE employee_questions SET status = 'reply_drafted', reply_item_id = ? WHERE id = ?",
                     (item.id, qid))
        audit.append(user.id, "question.reply_draft", "employee_question", qid,
                     {"template": template, "lang": lang, "item_id": item.id}, conn=conn)
    return item


def mark_answered(conn: sqlite3.Connection, qid: str) -> None:
    """Called by the executor's send handler, inside its transaction, once the reply really went out."""
    conn.execute("UPDATE employee_questions SET status = 'answered' WHERE id = ?", (qid,))

"""Generate the FICTIONAL employee handbook PDF indexed by P1's HR Answer Desk.

Run (from repo root):  backend\\.venv\\Scripts\\python.exe data\\handbook\\make_handbook.py
Output: data/handbook/handbook.pdf + data/handbook/sections.json (section -> page, for retrieval eval)

Company, people and policies are invented for the demo. Not legal advice.
"""
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent
COMPANY = "Carthago Data Systems SARL (fictional)"

SECTIONS: list[tuple[str, list[str]]] = [
    ("1. Working hours", [
        "The standard working week is 40 hours, Monday to Friday, from 08:30 to 17:30 with a one-hour lunch break.",
        "During the summer schedule (1 July to 31 August) and during Ramadan, working hours are 08:00 to 14:00. "
        "Managers publish the exact dates by internal memo at least two weeks in advance.",
        "Overtime must be approved in writing by the line manager before it is worked. Approved overtime is paid at "
        "125% of the hourly rate for the first 8 hours per week and 150% beyond that.",
    ]),
    ("2. Annual leave", [
        "Every employee earns 2 working days of paid annual leave per month of service, i.e. 24 working days per year.",
        "Leave requests are submitted in HireGuard at least 10 working days before the first day of leave. "
        "Requests of 3 days or fewer may be submitted 2 working days in advance.",
        "Up to 6 unused days may be carried over to the next year; they must be taken before 31 March. "
        "Days not carried over are lost unless the company refused the leave for business reasons.",
        "A leave confirmation document can be requested in HireGuard once the leave is approved.",
    ]),
    ("3. Public holidays", [
        "The company observes all Tunisian national and religious public holidays. The list for the year, including "
        "the expected dates of Eid al-Fitr, Eid al-Adha, Ras el Am el Hijri and the Mouled, is published each January.",
        "Employees required to work on a public holiday receive a compensatory day off within 30 days.",
    ]),
    ("4. Sick leave", [
        "Employees who are ill must inform their manager before 10:00 on the first day of absence.",
        "A medical certificate is required for any absence longer than 2 consecutive days and must be sent to HR "
        "within 48 hours. Certificates are handled only by HR and are never shared with the line manager.",
        "The company maintains full salary for up to 30 days of certified sick leave per calendar year, "
        "in addition to CNSS allowances.",
    ]),
    ("5. Maternity, paternity and family leave", [
        "Maternity leave is 14 weeks with full pay, of which at least 6 weeks are taken after the birth.",
        "Paternity leave is 7 working days with full pay, to be taken within 30 days of the birth.",
        "Employees are entitled to 3 days of paid leave for their own marriage and 3 days for the death of a close "
        "family member (parent, spouse, child, sibling).",
    ]),
    ("6. Remote work", [
        "Employees whose role allows it may work remotely up to 2 days per week, agreed with their manager.",
        "Remote work requires a company laptop, the company VPN and full-disk encryption. Personal devices must "
        "never be used to access candidate or employee data.",
        "A monthly internet allowance of 40 TND is paid to employees who work remotely at least 4 days per month.",
    ]),
    ("7. Expenses and travel", [
        "Business expenses are reimbursed within 15 days of submitting receipts in the expenses tool.",
        "Travel within Tunisia is reimbursed at 0.450 TND per kilometre for personal vehicles, or at the actual "
        "cost of a louage or train ticket. Meals during travel are reimbursed up to 35 TND per day.",
        "International travel must be approved by the department head and booked through HR.",
    ]),
    ("8. Training and development", [
        "Each employee has a training budget of 1,200 TND per year for courses, certifications and conferences.",
        "Training requests are approved by the line manager and HR. Employees who leave within 12 months of a "
        "training costing more than 2,000 TND may be asked to repay a pro-rata share, as set out in their contract.",
    ]),
    ("9. HR documents and certificates", [
        "Work certificates (attestation de travail), salary certificates (attestation de salaire) and leave "
        "confirmations are requested in HireGuard under My documents.",
        "Documents are generated from official templates and released after one HR check, usually within one "
        "working day. Released documents carry a verification code.",
        "Payslips are available on the 28th of each month. Questions about your own salary are handled "
        "confidentially by the HR team, not by the Answer Desk.",
    ]),
    ("10. Code of conduct", [
        "Employees treat colleagues, candidates and clients with respect. Harassment and discrimination on any "
        "ground, including gender, origin, region, religion or disability, are prohibited.",
        "Gifts from suppliers or candidates above 100 TND in value must be declared to HR.",
        "Conflicts of interest, including recruiting a relative, must be declared before the process starts.",
    ]),
    ("11. Data protection", [
        "Candidate and employee personal data are processed in line with Organic Law 2004-63 on the protection of "
        "personal data. Access is limited to the people who need it for their role.",
        "CVs of rejected candidates are deleted after 24 months unless the candidate agrees to a longer retention.",
        "Any suspected data breach must be reported to the security team within 1 hour of discovery.",
    ]),
    ("12. Grievances and contacts", [
        "An employee with a complaint first raises it with their manager. If it is not resolved within 10 working "
        "days, or if it concerns the manager, it may be raised with HR in writing.",
        "HR contact: hr@carthago-data.example. Security team: security@carthago-data.example.",
    ]),
]


def build():
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading2"], spaceBefore=6, spaceAfter=8)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=8)
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=24)

    page_map: dict[str, int] = {}

    class Doc(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == "h":
                page_map[flowable.getPlainText()] = self.page

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 1.2 * cm, f"{COMPANY} · Employee Handbook 2026 · fictional demo document")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Spacer(1, 5 * cm),
        Paragraph("Employee Handbook 2026", title),
        Paragraph(COMPANY, styles["Heading3"]),
        Spacer(1, 1 * cm),
        Paragraph("This handbook is a fictional document created for the HireGuard hackathon demo. "
                  "All names, amounts and policies are invented.", body),
        PageBreak(),
    ]
    for i, (heading, paras) in enumerate(SECTIONS):
        story.append(Paragraph(heading, h))
        story += [Paragraph(p, body) for p in paras]
        if i % 2 == 1:
            story.append(PageBreak())

    pdf = OUT / "handbook.pdf"
    Doc(str(pdf), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="Employee Handbook 2026", author=COMPANY).build(story, onFirstPage=footer, onLaterPages=footer)
    (OUT / "sections.json").write_text(json.dumps(page_map, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {pdf} ({len(page_map)} sections)")


if __name__ == "__main__":
    build()

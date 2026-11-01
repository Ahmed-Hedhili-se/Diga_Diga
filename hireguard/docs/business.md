# Venidis: the business case, with its evidence level

Status on 1 Nov 2026: **no customer has been interviewed and no pilot is agreed.** Everything below is either sourced
([evidence.md](evidence.md), ids E1 to E11), measured (`eval/results/*.json`), or labelled *assumption* or *hypothesis*. The calls that
would turn hypotheses into evidence are prepared in [discovery/](discovery/call_script.md).

## 1. Market

- **Base:** about 2,200 active ICT companies and about 40,000 direct jobs in Tunisia (E7), an average of about 18 staff per company (our calculation).
- **Beachhead:** engineering firms and IT-services companies with 50 or more staff. Taking 5% to 10% of 2,200 gives **about 110 to 220 firms** (assumption: replace it with a count from a real directory).
- **Order of magnitude:** 150 firms paying 400 TND a month is 720,000 TND a year (our calculation, a hypothesis).
- **Plainly:** Tunisia alone is a small market. The Maghreb and EU-facing IT-services firms are untested hypotheses; no source in this file supports their size.

## 2. Pricing hypotheses (TND per month, to be validated in interviews)

| Plan | For | Price | Anchor |
|---|---|---|---|
| Pilot | 1 open role, 3 months, up to 300 CVs | Free | Cost to serve is small: about $0.003 of compute per CV if the GPU stays busy (E11, our measured throughput) |
| SME | Up to 100 employees | 150 to 400 | An Odoo seat is about 33 TND a month (E8, at about 3 TND per USD) |
| Company | Up to 500 employees, on-premises GPU | 600 to 1,200, plus setup | A regional SaaS ATS is 2,500 to 3,750 TND a month, a vendor figure to read as a ceiling (E9) |

## 3. Return on investment

Assumptions: **4 minutes of recruiter time per CV** (assumption); **14.2 TND an hour** (2,500 TND gross a month from E10, which has fewer than 20
respondents, divided by 176 hours; assumption); **5 days faster per hire** at **180 TND a day** of vacancy cost (both assumptions, the second is a demo value).
You can change every one of them on the Money page of the product.

| | Small | Mid | Large |
|---|---|---|---|
| Roles a year | 5 | 20 | 60 |
| CVs per role | 100 | 150 | 200 |
| Plan price per year (150 / 400 / 1,000 TND a month) | 1,800 | 4,800 | 12,000 |
| Screening value (TND) | 473 | 2,840 | 11,360 |
| Faster-hiring value (TND) | 4,500 | 18,000 | 54,000 |
| Total value (TND) | 4,973 | 20,840 | 65,360 |
| Total value divided by price | 2.8 | 4.3 | 5.4 |
| Screening only, divided by price | 0.3 | 0.6 | 0.9 |

**Read it honestly.** Screening time alone does not pay for the plan: in Tunisia a recruiter's hour is cheap. The case rests on the
faster-hiring row, which is the least evidenced number here (an assumption, to be tested in the calls), and on a safer process and AI Act readiness
for firms that serve EU clients (E6: 2 Dec 2027 under the agreed delay, not yet confirmed as final).

*Workload scenario (hypothesis to check in calls).* If a Tunisian recruiter lost the US average of 9 hours a week to bad applications (E3, large US employers),
that is 468 hours a year, about 6,650 TND at 14.2 TND an hour (our calculation). We have no Tunisian figure for it.

## 4. Competition

| Alternative | What it is | Relation to Venidis |
|---|---|---|
| Job boards (for example Tanitjobs, Keejob) | They supply CVs | Not screening layers (to confirm in the calls) |
| Recruitee, Odoo Recruitment, regional or custom ATS | Hiring systems that hold candidates and stages | Venidis is a layer on top of an ATS or Odoo, not a replacement |
| A generic LLM screener | The CV text goes into one prompt | The measured baseline on our test: hidden-text attacks changed a result in 13 of 40 cases, against 3 of 40 for Venidis |

## 5. Risks and what we do not claim

- **No demand evidence yet.** Not one HR manager has told us this is a problem they would pay to solve.
- **Synthetic CVs only.** Every measurement uses generated CVs and emails, with attacks written by our team. Real CVs are untested.
- **PDF only.** `check_upload` rejects anything that does not start with `%PDF-`. A scanned PDF with no text goes to a person. Word files are refused.
- **A GPU is a barrier for a small company.** On-premises means hardware; a managed host in Tunisia is not built.
- **Arabic is weaker, and our own audit flags it.** Skill F1 is 0.80 on Arabic CVs against about 0.97 on French and English, and in the group audit through the model Arabic CVs were shortlisted 1 time in 33 against 30 in 103 for French (adverse-impact ratio 0.10, p = 0.001). In Tunisia this is a central risk, not a corner case.
- **The product name is not trademark-cleared** (`brand/README.md`).
- **The AI Act date** (2 Dec 2027) must be confirmed as published in the Official Journal before anyone says "final".
- **Visible manipulation still works.** Text written in plain sight changed a result in 7 of 14 tests (the naive screener, 8 of 14). Human review stays essential.
- **We do not claim** compliance with the AI Act, GDPR or Law 2004-63, productivity gains for any team, customers, or savings that someone has not measured.

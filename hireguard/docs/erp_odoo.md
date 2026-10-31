# Odoo ERP connector

HireGuard sits in front of Odoo as the secure AI layer. Odoo stays the system of record: applicants, CVs,
stages and calendars live there. HireGuard reads from Odoo, screens the data the same way it screens an upload,
and writes back only after a human has approved the action.

```
Odoo Recruitment (applicants + PDF CVs) ──read──► Sanitizer → Detector → Extractor → Validator → Scorer
Odoo Calendar (busy events)            ──read──► interview slots that skip busy times
                                                        │
                                              Approval queue (human)
                                                        │
Odoo ◄──write── Executor (ONLY after approval): move stage, post note, log email, create calendar event
```

Code: [backend/app/erp/](../backend/app/erp/). Tests: [backend/tests/test_erp_odoo.py](../backend/tests/test_erp_odoo.py)
(they run against an in-process fake Odoo, so no Odoo is needed).

## Security rules

1. **ERP data is untrusted.** Every CV from Odoo goes through `pipeline.service.process_cv`, the same path as an
   upload. A poisoned CV stored in Odoo shows up in the Security Center like any other.
2. **Writes to Odoo exist only as executor handlers** (`erp/handlers.py`). No route writes to Odoo.
3. **All or nothing.** If Odoo fails while an approved item runs, the executor returns HTTP 502, the local
   transaction rolls back (no outbox row, no booked slot) and the item stays `approved`, so it can be re-run.
   A re-run reuses the interview event if it was already created.
4. **Least privilege.** The Odoo bot user has *Internal User* + *Recruitment / Officer* only and authenticates with
   an API key from `.env`.
5. **No model-generated text reaches Odoo.** Notes are fixed templates. Email subjects and bodies (which come from
   typed-slot templates) are HTML-escaped.
6. **Off by default.** With `HG_ODOO_ENABLED=0` nothing is installed and the app behaves exactly as before.
7. **Reads may degrade, writes never do.** If Odoo is down, interview slots fall back to the local calendar;
   an approved write fails with 502 instead.
8. ERP data is never used to train any model.

## What is mirrored to Odoo

| Approved action      | Local effect (unchanged)        | Odoo effect                                                                  |
|----------------------|---------------------------------|------------------------------------------------------------------------------|
| `shortlist_commit`   | scores committed                | linked applicants move to *Shortlisted (HireGuard)*, note with the rubric score |
| `email_send`         | outbox row                      | internal note with the email (or real email with `HG_ODOO_SEND_EMAIL=1`)     |
| `interview_booking`  | slot booked, interview created  | `calendar.event` on the recruiter's calendar, invite logged on the applicant |
| `offer`              | outbox row                      | same as `email_send`                                                         |

Only candidates imported from Odoo (table `erp_links`, ids `CAND-ODOO-<applicant id>`) are mirrored; local
uploads are left alone. Interview events are created for every booking so the Odoo calendar stays complete.

## Run it

Needs Docker.

```powershell
docker compose -f odoo/docker-compose.yml up -d     # Odoo 17 on http://localhost:8069 (first boot: ~1 min)
python eval/gen_cvs.py --pdf                       # optional: generated CVs to import
python odoo/seed_odoo.py                           # bot user, stage, jobs, applicants, busy events
```

Paste the printed `HG_ODOO_*` lines into `.env`. For anything beyond a local demo, log in to Odoo as the bot,
create an API key (*Preferences → Account Security → New API Key*) and use it as `HG_ODOO_API_KEY`.
Then `.\run.ps1`, open **Candidates**, click **Import from Odoo**, propose a shortlist, approve it as an HR
manager, run it, and check the applicant's stage and chatter in Odoo.

## Configuration

| Variable                   | Default                     | Meaning                                                     |
|----------------------------|-----------------------------|-------------------------------------------------------------|
| `HG_ODOO_ENABLED`          | `0`                         | `1` turns the connector on                                  |
| `HG_ODOO_URL`              | `http://localhost:8069`     | Odoo base URL                                               |
| `HG_ODOO_DB`               | `hireguard`                 | Odoo database                                               |
| `HG_ODOO_USER`             | `hireguard-bot@example.tn`  | bot login                                                   |
| `HG_ODOO_API_KEY`          | (empty)                     | bot API key                                                 |
| `HG_ODOO_TIMEOUT_S`        | `10`                        | socket timeout per call                                     |
| `HG_ODOO_SHORTLIST_STAGE`  | `Shortlisted (HireGuard)`   | stage for approved shortlists (created on first use if missing) |
| `HG_ODOO_RECRUITER_LOGIN`  | the bot user                | whose calendar blocks interview slots                       |
| `HG_ODOO_SEND_EMAIL`       | `0`                         | `1` = Odoo emails the applicant instead of only logging a note |

## Endpoints

| Method | Path                               | Roles                         | Notes                                                    |
|--------|------------------------------------|-------------------------------|----------------------------------------------------------|
| GET    | `/api/erp/status`                  | recruiter, hr_manager, admin  | `{enabled, connected, url, db, uid?, server_version?, error?}` |
| GET    | `/api/erp/jobs/{job_id}/applicants`| recruiter, hr_manager         | Odoo applicants for the job, with an `imported` flag     |
| POST   | `/api/erp/jobs/{job_id}/import`    | recruiter, hr_manager         | imports new or changed CVs; `{job_id, imported, skipped}` |

404 if the job is unknown, 409 if the connector is disabled, 502 if Odoo is unreachable or refuses the call.
An import skips applicants with no PDF, a PDF over `HG_MAX_UPLOAD_BYTES` (checked before download), an
unchanged PDF (same checksum), or data the pipeline rejects (bad name, email or PDF).

# Business-side notes and blocked items

Working notes from the business pass of 1 Nov 2026. Nothing here is a claim for buyers.

## Left as it is, on purpose

- **Vacancy cost per job** (`daily_vacancy_cost_tnd` in `backend/app/scoring/jobs.py`, 90 to 220 TND a day) is a fictional demo value. There is no route or screen
  to edit it per job (the only editable money setting is the hourly HR cost), so it stays hardcoded. The Money page labels the number as an
  estimate, and the new ROI card lets a visitor type their own cost of an empty seat. To make it editable per job: add a field to the job
  record, a `PUT /jobs/{id}` setting, a permission, an audit event and a screen. That is a product change, not a documentation fix.
- **`MINUTES_PER_UNIT`** (6 minutes per CV, and so on) feeds "ROI to date" and is an unsourced estimate. It was not changed, as agreed. The Money page now says
  so under the tiles. The ROI card uses its own labelled assumption (4 minutes per CV).
- **The old product name** (HireGuard, HR Nexus) still appears in `docs/pitch.md`, `docs/architecture.md`, the `hireguard/` folder, the `HG_*` settings and the
  Odoo stage default. Rename once the name is cleared (`brand/README.md`).

## Things to check by hand

- E1 to E11 in `docs/evidence.md` were supplied by the team; only the URLs' reachability was checked. GlobeNewswire (E3) answers 403 to automated requests.
- `docs/business.md`: 5% of 2,200 firms is 110, so the beachhead range reads 110 to 220 (the brief said 100 to 220).
- Whether the omnibus delay (E6) was published in the Official Journal.

## Blocked

(nothing yet)

## Run the 12 implicit attacks through the real model (to do by hand)

The code-path result (12 of 12) is in `docs/evaluation.md`. Whether the model obeys such text is not measured yet. With the Modal endpoint warm and `.env.modal` loaded:

```powershell
cd hireguard
$py = "backend\.venv\Scripts\python.exe"
& $py eval\gen_attacks_implicit.py
& $py eval\harness.py --extraction llm --only attacks_implicit --summary evalesults\summary_implicit.json
```

Read `attack_success` and `by_channel` in the new file, quote it only as "through the model, 12 synthetic implicit attacks", and add the row to `docs/evaluation.md`.
A note on the generator: a payload longer than the cover image leaves a visible fragment in the page margin. That is a flaw in a test file, not a sanitizer miss, and `under_image` payloads are now cut to fit.

# HR interview guide (10-minute call)

Owner: Ahmed. Purpose: replace every business **TBD** in `docs/pitch.md` with a number someone actually gave us.

Rules:
- Interview HR people, not candidates.
- Record **no personal data**: company size band and sector only, no names in the notes.
- Ask for estimates in their own units and write them down exactly as said.

## Opening (30 seconds)

"We're building an HR assistant for a hackathon. It sorts CVs and drafts replies, and a person approves everything. Ten minutes, no names recorded. Can I ask about your hiring?"

## Questions

| # | Ask | Feeds |
|---|---|---|
| 1 | How many open roles do you have right now, and how many CVs does one role usually get? | Volume line on the problem slide |
| 2 | How long does it take you to read and sort **one** CV, in minutes? | `MINUTES_PER_UNIT["cv_screening"]` in `backend/app/scoring/money.py` |
| 3 | How many candidate emails a day? How long to answer one? | `MINUTES_PER_UNIT["emails"]` |
| 4 | From opening a role to a signed offer, how many days? What's your target? | Days to fill, next to SHRM's 39 |
| 5 | What does a day with the seat empty cost you (lost billing, overtime, delays)? Rough TND is fine | `daily_vacancy_cost_tnd` in `scoring/jobs.py` |
| 6 | How often does a candidate turn down an offer, and what's the usual reason? | Offer-fit slide (we expect salary) |
| 7 | Do you use any AI or software to screen CVs today? What worries you about it? | Problem and positioning slides |
| 8 | Would you let an AI read CVs if a person approves every action and candidate data never leaves your office? | Positioning |
| 9 | What would you pay per month for this, for your company size? (anchor: "less than a day of an HR salary?") | Pricing table |
| 10 | Would you try it on one open role for 3 months? | "Pilots asked" on the business slide |

## Notes table (one row per call)

| Call | Sector | Employees (band) | CVs per role | Min per CV | Emails per day | Min per email | Days to fill (target) | TND per empty day | Decline reason | Price said (TND/month) | Pilot? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | | | |
| 2 | | | | | | | | | | | |
| 3 | | | | | | | | | | | |

## Turning notes into pitch numbers

- Use the **median** across calls, and say "n = calls" next to every number.
- Put minutes per CV and per email into `MINUTES_PER_UNIT`, and the cost of an empty day into the job's `daily_vacancy_cost_tnd`. Then note the source in the docstring ("median of n HR interviews, 1 Nov").
- Pilots: "k of n HR managers asked for a pilot". With fewer than 3 calls, show the quotes instead of a percentage.

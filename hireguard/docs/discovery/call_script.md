# Customer discovery: call script

Goal: replace every hypothesis in [`business.md`](../business.md) with something a real person told us. 8 to 10 calls of 20 minutes,
with engineering firms and IT-services companies of 50 or more staff. Log each call in [`call_log.csv`](call_log.csv) the same day, then run
`python scripts/discovery_summary.py` to see what the pitch is allowed to say.

## The 10 questions (ask about what happened, not what might)

1. Tell me about the last engineer you hired: how many CVs came in, who read them?
2. How long did reading take, where was time lost?
3. How many days was the seat empty, what did that cost?
4. Which tools do you use (Excel, Odoo, job board, ATS)?
5. Do you use AI to read CVs or answer candidates, what happened?
6. Have you seen a manipulated or suspicious CV?
7. What share of CVs are in Arabic or mixed languages, how do you handle them?
8. Who approves an offer and how long does it take?
9. Could CVs be processed on a server outside the company, outside Tunisia?
10. If a tool did this and you approved every action, what would it have to cost to try it on one open role?

## The 6 rules

1. **Write the exact words.** A quote you paraphrase is a quote you invented.
2. **Never claim the AI replaces people.** The product prepares work; a person approves every action.
3. **Show the one-minute demo only after question 10.** Otherwise you collect compliments, not answers.
4. **Ask for a three-month pilot on one open role.** Use the [pilot letter](pilot_letter_fr.md).
5. **Ask for two referrals.**
6. **Never invent or round up.** A blank is better than a guess. "I did not ask" is a valid entry.

## After the call

- Fill `call_log.csv` (one row per call; leave a cell blank when you do not know).
- `would_pilot` is `yes`, `no` or `maybe`. Only `yes` counts as a pilot asked, and only if they said it in their own words.
- Note the date of the call, not the date you typed it.
- Never write a count in the pitch that the summary script does not print.

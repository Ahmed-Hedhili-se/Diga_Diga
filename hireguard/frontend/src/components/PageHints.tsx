// "Words on this page": a short plain-language glossary at the bottom of each page, for the terms that
// read as jargon to someone who is not a recruiter, statistician or security engineer. One sentence each.

type Hint = [term: string, meaning: string];

const HINTS: Record<string, Hint[]> = {
  "/overview": [
    ["Proposed / committed", "A proposed score is a suggestion from the system. It becomes committed only after a person approves the shortlist."],
    ["Needs a human check", "The system was unsure (for example the AI could not read the CV), so a person must look before the score counts."],
    ["Attack stripped", "The CV contained hidden text meant to fool the screening. It was removed before scoring."],
    ["Connected systems", "The AI model reads CVs and emails; Odoo is your HR system. Green means HireGuard can reach it right now."],
  ],
  "/candidates/upload": [
    ["Screening", "The CV is checked for hidden text, read by the AI, checked against the visible text, then scored by fixed rules."],
    ["Talent pool consent", "The candidate agrees to be considered for other jobs later. It expires after two years and can be withdrawn."],
  ],
  "/candidates": [
    ["Rubric", "The scoring rules for a job: which skills count and how much, minimum experience, degree and languages."],
    ["Rescore", "Recalculate every candidate's score with the current rubric. Scores stay suggestions until a shortlist is approved."],
    ["Borderline", "Small changes to the rubric weights would move this candidate in or out of the shortlist. Review them one by one."],
    ["Offer fit", "Whether the candidate's own salary and work conditions match what the job offers. It never changes the score."],
    ["Fills a gap", "The candidate has a skill that nobody, or only one person, on the team has today."],
    ["Only listed", "A skill named in a list but not backed by any dated job. It counts for much less, because stuffing keywords is easy."],
  ],
  "/rubrics": [
    ["Weight", "How much a skill or section counts. Weights are compared with each other, so doubling all of them changes nothing."],
    ["ESCO skill", "A skill from the European standard skills list, so the same skill is always called the same thing."],
    ["CEFR level", "The European language scale: A1 beginner up to C2 near-native."],
  ],
  "/inbox": [
    ["Lane", "Where an email goes: routine (a draft reply is prepared), needs a person, or suspicious (held, nothing is sent)."],
    ["Intent / urgency", "What the email is about and how soon it needs an answer. The AI suggests them; fixed rules choose the lane."],
    ["SPF, DKIM, DMARC", "Checks that an email really comes from the address it claims. A failure is a sign of a faked sender."],
    ["Held email", "Kept back because it looks risky. Releasing it needs an HR manager's approval."],
  ],
  "/approvals": [
    ["High-risk item", "Something that is hard to undo, such as an offer or a document. It is reviewed alone, never in a batch."],
    ["Batch", "Several routine items of the same kind reviewed together. Batches shrink automatically if reviewers start missing mistakes."],
    ["Test item", "About one item in 20 is a deliberately wrong copy, to check items are really read. Approving it runs nothing."],
    ["Execute", "After approval, the action is carried out (email sent, interview booked). Nothing happens before this step."],
  ],
  "/interviews": [
    ["Scorecard", "The same four questions for every candidate, rated 1 to 4, so interviews can be compared fairly."],
    ["Working with others", "Rate examples the candidate gave of working with others, as the job needs. Not whether you liked them."],
  ],
  "/team": [
    ["Single holder", "Only one person on the team has this skill. If they leave or are away, the team loses it."],
    ["Groups of 5 or more", "Numbers about fewer than 5 people are hidden, so nobody can work out who a figure is about."],
    ["Median / p95", "Median is the typical time; p95 is the slow case: 95 out of 100 cases are faster than this."],
    ["Bottleneck", "The hiring step where candidates wait the longest."],
    ["No match", "An employee asked the handbook something it does not answer. Many no-matches on a topic mean the handbook needs a section."],
  ],
  "/questions": [
    ["Routed question", "A personal question (pay, leave, contract) the handbook cannot answer. It comes to HR instead."],
    ["Template reply", "Replies use fixed wording and still need approval, so nothing personal is sent by mistake."],
  ],
  "/answer-desk": [
    ["Extract", "The exact sentences from the handbook, word for word, with the section they come from. Nothing is made up."],
    ["Ask HR", "The handbook does not answer this. Your question goes to HR instead of getting a guessed answer."],
  ],
  "/documents": [
    ["Released", "An HR manager approved the document, so you can download it now."],
    ["Template", "Documents are filled from fixed, reviewed templates, never written freely."],
  ],
  "/security": [
    ["Hidden text", "Text in a CV that people cannot see but software can, used to trick automatic screening."],
    ["Range (interval)", "With few test samples a percentage is uncertain; the range shows where the true value probably is."],
    ["Selection ratio", "The least-chosen group's shortlist rate divided by the most-chosen group's. 1.00 is equal; under 0.80 is a warning."],
    ["Activity record", "A tamper-evident diary of important actions. Changing an old entry breaks the chain and shows up."],
  ],
  "/money": [
    ["Cost of vacancy", "An estimate of what an unfilled job costs per day, added up since it opened."],
    ["Hours saved", "Time HR would otherwise spend screening, answering emails and preparing documents by hand."],
    ["ROI (TND)", "Here: the hours saved multiplied by the hourly staff cost you set. It does not subtract what HireGuard costs."],
  ],
  "/users": [
    ["Role", "What a person can do. Admins manage accounts but cannot read candidate files or approve HR actions."],
    ["Lockout", "After several wrong passwords the account is paused for a while, to stop password guessing."],
  ],
};

export default function PageHints({ path }: { path: string }) {
  // longest matching prefix, so /candidates/upload gets its own hints rather than the Candidates ones
  const key = Object.keys(HINTS)
    .filter((k) => path === k || path.startsWith(k + "/"))
    .sort((a, b) => b.length - a.length)[0];
  const hints = key ? HINTS[key] : null;
  if (!hints) return null;
  return (
    <aside className="page-hints" aria-label="Words on this page">
      <h2>Words on this page</h2>
      <dl>
        {hints.map(([term, meaning]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

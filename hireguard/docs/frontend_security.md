# Frontend security review (Yasmina)

The browser is not an enforcement layer. Every check below is about what the UI shows and sends; the server decides
(RBAC matrix `backend/app/auth/permissions.py`, enforced by `tests/test_rbac.py`). Reviewed on branch `team`,
2026-11-01. Tests: `cd hireguard/frontend; npm test` (Vitest + jsdom, 11 tests) and
`backend/tests/test_ui_api_contract.py`.

## Checklist

| Area | Control | Evidence | Status |
|---|---|---|---|
| Hostile text | Candidate, employee and email text is rendered as React text nodes only. No `dangerouslySetInnerHTML`, `innerHTML`, `eval` or `new Function` in `src/` | `grep` over `frontend/src` (empty); test "candidate CV text with markup creates no element" | pass |
| Hostile text in errors | Server error details are shown as text | test "a hostile server error message is shown as text" | pass |
| PDF preview | pdf.js 4.8.69 renders to a canvas with `isEvalSupported: false` (blocks the font-eval class of pdf.js bugs); worker from the same origin; no annotation or script layer | `components/PdfViewer.tsx` | pass |
| Downloads | Fetched as a blob with the session cookie, saved via a temporary object URL that is revoked after 1 s; the server sends `Content-Disposition: attachment` and `nosniff` | `api.ts` (`downloadFile`), API.md | pass |
| CSP | `default-src 'self'; script-src 'self'`; no inline script; `object-src 'none'`; `frame-src 'none'`; `frame-ancestors 'none'` | `backend/app/security.py` | pass; `/api/docs` keeps a relaxed CSP, so disable it in production (pentest O1, still open) |
| Third-party code | 4 runtime dependencies, all pinned: react 18.3.1, react-dom 18.3.1, react-router-dom 6.28.0, pdfjs-dist 4.8.69. Nothing is loaded from a CDN at runtime | `package.json`, CSP | pass |
| Session | HttpOnly SameSite=Strict cookie; every non-GET sends `X-CSRF-Token`; any 401 outside login signs the user out of the UI; idle timer warns, then signs out | tests "mutations carry the CSRF token", "a 401 on any call signs the user out" | pass |
| Permission denied | A 403 is shown as "Permission denied (403)" with the reminder that hidden buttons are not the protection; controls without the permission are not rendered | tests "error states", "a control without the permission is not rendered" | pass |
| Errors vs empty | A failed request never shows the empty message ("No candidates yet") | test "a failed list request shows the failure, never the empty message" | pass after fix Y1 |
| Uploads | The UI rejects files over 5 MB, over 6 pages or not PDF before sending; the server's `check_upload` stays authoritative | `pages/Candidates.tsx` (`MAX_BYTES`, `MAX_PAGES`), `pipeline/service.py` | pass |
| Consequential actions | Every approve, execute, shortlist, rescore, invitation, removal or offer goes through `ConfirmButton` | test "ConfirmButton runs the action only after the explicit confirm" | pass |
| Honest copy | Scores say "proposed" until committed; the panel says code computes and a person approves; offline (ground-truth) extraction is labelled; evaluation numbers carry their mode | `pages/Candidates.tsx`, `pages/SecurityCenter.tsx` | pass after fixes Y2–Y4 |
| UI/API drift | All 47 paths the frontend calls exist in the backend route table | `tests/test_ui_api_contract.py` | pass |
| Accessibility | Skip link, visible focus rings, labelled nav and main, keyboard-selectable ranking rows, native modal dialog, `prefers-reduced-motion`, dark mode | `styles.css`, `App.tsx`, `components/ui.tsx` | pass by code review; not yet tested with a screen reader |
| Responsive | Breakpoints at 1000 px and 720 px; tables scroll inside `.table-wrap` | `styles.css` | pass by code review; not yet tested on a phone |

## Findings

| # | Severity | Finding (repro) | Boundary | Owner | Fix | Retest |
|---|---|---|---|---|---|---|
| Y1 | medium | Make `/api/documents/mine` (or any list) return 500: the page showed the error **and** "No requests yet", so a failure looked like no data. 7 pages affected | UI honesty | Yasmina | `6f1c947`: every list hides its empty message on error; `ErrorBox` names the failure | test passes |
| Y2 | medium | Open a candidate with a visible injection: the panel said every injection "was stripped before extraction and did not change the score". Visible text is read by the model, and the measured run moved 3/40 attacked CVs | UI honesty | Yasmina | `6f1c947`: copy separates removed hidden text from flagged visible text; no promise the score is unchanged | manual review |
| Y3 | high | Security Center > Evaluation served mnasri's oracle-mode summary (0/40 attacks, 0/89 twins) with no mode label, so it read as model robustness. The real model moved 3/40 and 26/90 | Claims / pitch | Yasmina, Hedhili | `abf0777`: oracle results moved to `summary_oracle.json`; `5f87c67`: every section shows its mode and a warning for oracle | manual review |
| Y4 | low | A CV seeded in offline mode looked exactly like a model extraction | UI honesty | Yasmina, Rayen | `6f1c947`: `CandidateRow.extraction` exposed; "offline extraction" badge and alert | manual review |
| Y5 | medium | Team-gaps teams have 4 members, below the k >= 5 rule for team-level output; "only one person holds X (1 of 4)" can point to a colleague | Privacy (HR Nexus) | Rayen, Ahmed | UI shows team size and a small-team caveat. **Open:** the backend should suppress or coarsen counts for teams under 5 | open |
| Y6 | info | mnasri's offer-fit, offer, rediscover and talent-pool endpoints had no screens | Workflow | Yasmina | `ad0688d`: Talent pool and Offer fit sections | build + contract test |

Open items: Y5 (backend decision), `/api/docs` CSP in production, a screen-reader pass and a phone pass.

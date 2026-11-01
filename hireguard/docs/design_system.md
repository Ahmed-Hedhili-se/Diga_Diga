# HireGuard design system

The interface uses neutral surfaces first and reserves color for clear meaning.
The same components and semantic tokens are used in light and dark themes.

## Color tokens

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `--bg` | `#F6F7FB` | `#0B1020` | Application background |
| `--surface` | `#FFFFFF` | `#121A2B` | Cards, tables, dialogs |
| `--surface-2` | `#F1F3F9` | `#18223A` | Inputs, table headers, hover |
| `--border` | `#E3E7EF` | `#26324D` | Borders and dividers |
| `--text` | `#0F172A` | `#E6EAF2` | Main text |
| `--muted` | `#5B6478` | `#9AA6BF` | Secondary text |
| `--primary` | `#4338CA` | `#818CF8` | Primary actions, links, focus |
| `--ok` | `#047857` | `#34D399` | Approved, safe, verified |
| `--warn` | `#B45309` | `#FBBF24` | Pending, caution, human review |
| `--danger` | `#B91C1C` | `#F87171` | Security alerts and destructive actions |
| `--info` | `#0369A1` | `#38BDF8` | Neutral information and AI drafts |
| `--evidence` | `#C7D2FE` | `rgba(129,140,248,.30)` | Candidate evidence highlights |
| `--hidden` | `#FDE68A` | `rgba(251,191,36,.28)` | Revealed hidden text |
| `--focus` | `rgba(67,56,202,.35)` ring | `rgba(129,140,248,.45)` ring | Visible keyboard focus |

Candidate scores use the single indigo ramp `--score-1` through `--score-5`.
Red is never used to communicate a low candidate score. Module identity colors
belong only to navigation icons, active indicators, and the page header chip.

| Module | Light identity | Dark identity |
|---|---|---|
| Candidates | `#4338CA` | `#A5B4FC` |
| Approvals | `#B45309` | `#FCD34D` |
| Inbox | `#0369A1` | `#7DD3FC` |
| Security Center | `#BE123C` | `#FDA4AF` |
| Money | `#047857` | `#6EE7B7` |
| Answer Desk | `#6D28D9` | `#C4B5FD` |
| My documents | `#0F766E` | `#5EEAD4` |
| Interview scorecard | `#1D4ED8` | `#93C5FD` |
| Users | `#334155` | `#CBD5E1` |
| Team insights | `#A21CAF` | `#F0ABFC` |

## Interaction and layout

- Theme preference is `system`, `light`, or `dark`; it is saved as
  `hireguard-theme` in local storage and applied with `data-theme` on `<html>`.
- Sidebar links are filtered by the permissions returned by the existing auth
  session. The compact sidebar and mobile navigation do not change route access.
- `Ctrl/Cmd + K` opens a page switcher containing only accessible pages.
- The page switcher and confirmations use the existing native `<dialog>`
  primitive for browser-managed focus and Escape handling.
- Buttons, cards, tables, alerts, and badges use shared CSS classes and tokens.
- Keyboard focus remains visible; reduced-motion preferences disable animations.
- At narrow widths the sidebar becomes a dismissible navigation drawer and
  dashboard grids collapse to a single column.

Use `/style-guide` in a development build while signed in with the existing
`users.manage` permission to preview shared components in both themes.

The authenticated workspace includes a permission-filtered **Examples to try**
tour. The Answer Desk also offers sample questions that populate the field
without submitting them; the user reviews and explicitly sends each query.
Opening a tour item does not approve, send, or release a workflow item.

## Typography, language and layout conventions

- **One interface font:** Figtree, for the interface and for every heading. The serif face (Literata) is only for text that reads like a
  document: CV extracts, an employee's question, and the sample CV on the sign-in page. Never for titles, numbers or controls.
- **Sidebar:** neutral (`--surface`, with a border). Identity colour appears only on the navigation icon and the active indicator.
- **Language and format:** the interface is English; dates and numbers use `en-GB` so they never mix a French date with English text.
  Greetings are plain ("Good morning"), with no playful copy.
- **Task first:** the page's main task comes first. On Candidates the ranking sits above the offer-fit and team-context cards.
- **Derived tokens:** `--border-strong`, `--primary-hover` and the `-soft` backgrounds are not in the table above. They are derived from it
  (a tint of the same hue) and live in `src/styles.css`.

## Conformance audit (1 Nov 2026)

Checked on the running interface in light and dark with screenshots of Overview, Candidates, Approvals, Security Center and Team, and by
computing contrast from the token values.

| Criterion | Status |
|---|---|
| Neutral surfaces first, colour only for meaning | Met. The paper tint, navy sidebar and yellow tab were removed |
| Tokens equal the table, light and dark | Met for every row |
| Single indigo score ramp, red never used for a low score | Met |
| Module colours only on navigation icons, active indicator, header chip | Met (colours come from the table, Team added) |
| Theme: system, light, dark, saved as `hireguard-theme` | Met |
| Same components in both themes | Met |
| Keyboard focus visible, reduced motion respected, drawer on narrow screens | Present in the stylesheet; not re-tested here |

WCAG AA contrast (4.5:1 for text), light / dark:

| Pair | Light | Dark |
|---|---|---|
| Text on surface | 17.9 | 14.4 |
| Muted text on surface | 5.9 | 7.1 |
| Button text on primary | 7.9 | 6.4 |
| Primary link on surface | 7.9 | 5.8 |
| OK / warning / danger / info text on its soft background | 4.8 / 4.5 / 5.6 / 5.2 | 6.9 / 7.8 / 5.2 / 6.3 |
| Primary on primary-soft (active navigation) | 7.1 | 4.6 |

Not covered: a screen-reader pass, automated accessibility testing, and the Interviews, Inbox, Money and Users pages.

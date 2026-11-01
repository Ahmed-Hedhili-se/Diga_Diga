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

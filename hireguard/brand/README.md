# Venidis: brand kit

*Read safely. Decide together.*

## The name

**Venidis** is a coined word, echoing the Latin *venire* (to come) and *videre* (to see): what arrives is seen before it is
trusted. That is what the product does with every CV and email. It is easy to say in French, Arabic and English, it has no
religious or negative reading that we could find, and it is not a dictionary word, so it can be owned.

### How we chose it (1 Nov 2026) and what this does not prove

| Check | Result |
|---|---|
| Web search for a company, product or app called "Venidis" | None found. Only unrelated near-matches (Vidis SA, a Polish audio-visual distributor) |
| Domains (registry lookup) | `venidis.com`, `.io`, `.ai`, `.app`, `.co`, `.org`, `.net` were all unregistered |
| Names rejected | **HR Nexus**: an HRMS vendor already uses it. **HireGuard**: no exact match, but close to TalentGuard, Hireguide and HireGround in the same industry. **Tabyin**: a live AI product uses it. **Attesta, Thiqa, Probato**: too close to existing HR or recruiting products. **Ravilum**: reads like a drug name (ravulizumab). **Nivetum**: close to Netum, an IT-services firm. **Kafil**: the sponsor in the *kafala* labour system |

**This is not a trademark clearance.** A web search cannot clear a mark. Before spending money on the name:
1. Search INNORPI (Tunisia), EUIPO TMview and the WIPO Global Brand Database, classes 9, 35, 42 (software, HR services, SaaS).
2. Check `venidis.tn` with the registry (ATI). Register the domains above now, they cost little.
3. Ask an IP lawyer for an opinion. If the name fails, change `src/brand.ts` in the frontend and `brand/build_logo.py` (`NAME`), then rerun the script.

The code still uses the old name in places that other people depend on (the `hireguard/` folder, `HG_*` settings, the default Odoo stage
`Shortlisted (HireGuard)`, the demo company name). Rename those in one pass **after** the name is cleared.

## The logo

![Venidis](venidis-logo.svg)

A **V** that narrows what arrives to a single point, with a **highlighter-yellow dot** above it: the evidence a human reviews. It
also reads as a head above shoulders, the person in the loop. The colours are the product's own (`docs/design_system.md`): indigo `#4338CA`
(primary), amber `#FBBF24` (the dot) and ink `#0F172A` (the wordmark). The wordmark is Figtree SemiBold (SIL Open Font License), converted to outlines.

| File | Use |
|---|---|
| `venidis-logo.svg` | Default: light backgrounds |
| `venidis-logo-on-dark.svg` | Navy or dark backgrounds |
| `venidis-mark.svg` | Avatar, favicon, app icon |
| `venidis-mark-on-dark.svg` | Mark on navy |
| `venidis-mark-mono.svg` | One colour (`currentColor`): stamps, fax, embossing |

Rebuild with `python brand/build_logo.py`. Rules: clear space of half the mark's height on every side; never recolour the dot,
stretch, rotate, outline or add effects; the minimum size for the mark is 16 px; do not put the full logo on a busy photo.

## Colour and type

Use the product's tokens, documented in `docs/design_system.md` and implemented in `frontend/src/styles.css`: neutral surfaces, indigo
`#4338CA` for actions, amber only for evidence and highlights, green/amber/red only for state. The interface and its headings use **Figtree**;
long document text (CV extracts, employee questions) uses **Literata**. For Arabic: Noto Sans Arabic.

## Voice

Plain, precise, calm. Say what is measured and what is not. Never promise what a human must decide.

| Say | Do not say |
|---|---|
| "Ranks CVs with the evidence highlighted" | "Selects the best candidate" |
| "Flags hidden and instruction-like text and limits what it can do" | "Blocks all malicious CVs" |
| "A person approves every action" | "Fully automated hiring" |
| "Shows which skills your teams hold, in aggregate" | "Improves team productivity" or "monitors employees" |
| "The model can run on your own servers" | "Your data never leaves" (true only when run on premises) |

Tagline options: **Read safely. Decide together.** (main) · *Every CV read. Every decision yours.* · *L'assistant RH qui lit sans obéir.* (French)

## Boilerplate

**Short (30 words):** Venidis is an HR assistant for Tunisian companies. It reads CVs and emails, ranks candidates with the evidence
highlighted, flags hostile content, and leaves every decision and action to a person.

**Long:** Venidis reads CVs and emails with a language model that has no tools and returns only typed fields. Code checks each
field against the visible text, a deterministic scorer ranks candidates and shows why, and a person approves every action, which is
recorded in a tamper-evident log. It runs on your own servers, works in French, English and Arabic, and connects to Odoo.

## Claims guardrails

Only claim what a result file shows, and say how it was measured. Today (synthetic test CVs, 1 Nov 2026, Qwen3-8B):
hidden-text attacks moved a result 3 of 40 times against 13 of 40 for a naive screener; hidden text was found 40 of 40 times with 0 false
alarms; spoofed emails were contained 15 of 15 times; skill extraction F1 was 0.94 (Arabic 0.80). **Always add the limits:** text written in plain
sight moved a result 7 of 14 times (the naive screener, 8 of 14), so human review stays essential. Do not use customer names, quotes, savings figures or
"trusted by" until there are customers who agreed to them. Do not call it compliant with the EU AI Act, GDPR or Law 2004-63: describe the controls, not a legal status.

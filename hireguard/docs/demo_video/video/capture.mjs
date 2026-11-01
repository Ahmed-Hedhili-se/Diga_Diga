// Screenshots of the running dashboard for the 3-minute demo video, taken through Chrome's DevTools protocol
// (Node 22+, no packages).
//
//   node capture.mjs --accounts <file> [--base http://localhost:5173] [--only id,id]
//
// <file> holds one "email password" pair per line, copied from the seed output; never commit it. The app must be running
// and freshly seeded (.\run.ps1 -Seed). Writes build/shots/<id>.png and build/shots.json: picture size and named target
// rectangles in picture pixels, which render.mjs zooms to and outlines. Steps that change data (offer draft, approval,
// refused run, Answer Desk questions, document request) run last, in the order a demo would do them. --only re-takes
// some shots and keeps the others; a step that changes data only works once per seed.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch, newTab, sleep } from "./cdp.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "build", "shots");
const MANIFEST = path.join(HERE, "build", "shots.json");
const W = 1536, H = 864, DPR = 2; // a 125% zoom on a 1920x1080 screen, with 2x pixels: sharp up to the stage's 1.6x zoom, and light on memory
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const BASE = arg("base", "http://localhost:5173").replace(/\/$/, "");
const ONLY = arg("only")?.split(",");
const accountsFile = arg("accounts");
if (!accountsFile) throw new Error("--accounts <file> is required");
const ACCOUNTS = Object.fromEntries(
  readFileSync(accountsFile, "utf8").split(/\r?\n/).map((l) => l.trim().split(/\s+/)).filter((p) => p.length === 2 && p[0].includes("@")),
);
const manifest = existsSync(MANIFEST) ? JSON.parse(readFileSync(MANIFEST, "utf8")) : {};

// Runs in every page before the app: light theme, no animations, and small DOM helpers.
const HELPERS = `(() => {
  try { localStorage.setItem("hireguard-theme", "light"); } catch {}
  const css = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}html{scroll-behavior:auto!important}";
  const add = () => { const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s); };
  document.head ? add() : document.addEventListener("DOMContentLoaded", add);
  const txt = (e) => (e.innerText || e.textContent || "");
  window.__hg = {
    q: (s, root = document) => root.querySelector(s),
    all: (s, root = document) => [...root.querySelectorAll(s)],
    find: (sel, needle, root = document) => [...root.querySelectorAll(sel)].find((e) => txt(e).includes(needle)) || null,
    findLast: (sel, needle, root = document) => [...root.querySelectorAll(sel)].filter((e) => txt(e).includes(needle)).pop() || null,
    // The innermost element containing the text (find() returns the outermost one for generic selectors like "div").
    deep: (sel, needle, root = document) => [...root.querySelectorAll(sel)].filter((e) => txt(e).includes(needle)).sort((a, b) => txt(a).length - txt(b).length)[0] || null,
    set(el, v) {
      const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, String(v));
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    },
    rect(el) { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; },
    union(...els) {
      const rs = els.filter(Boolean).map((e) => e.getBoundingClientRect());
      if (!rs.length) return null;
      const x = Math.min(...rs.map((r) => r.left)), y = Math.min(...rs.map((r) => r.top));
      return [x, y, Math.max(...rs.map((r) => r.right)) - x, Math.max(...rs.map((r) => r.bottom)) - y];
    },
    center(el) { el.scrollIntoView({ block: "center", behavior: "instant" }); },
    top(el, margin = 110) { el.scrollIntoView({ block: "start", behavior: "instant" }); window.scrollBy(0, -margin); }, // clears the sticky top bar
    idle: () => document.readyState === "complete" && !document.querySelector(".skeleton, [aria-busy='true']"),
  };
})();`;

class Page {
  constructor(cdp, sessionId, who) { Object.assign(this, { cdp, sessionId, who }); }
  send(method, params) { return this.cdp.send(method, params, this.sessionId); }
  async eval(expression) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(`${this.who}: ${r.exceptionDetails.exception?.description ?? r.exceptionDetails.text} in ${expression.slice(0, 120)}`);
    return r.result.value;
  }
  async waitFor(expression, ms = 25000) {
    const t0 = Date.now();
    let last, reloaded = false;
    while (Date.now() - t0 < ms) {
      try { if (await this.eval(expression)) return; } catch (e) { last = e; }
      // A page that has not shown what we wait for halfway through gets one fresh load of the same route.
      if (!reloaded && this.route && Date.now() - t0 > ms / 2) {
        reloaded = true;
        await this.send("Page.navigate", { url: BASE + this.route });
        await sleep(1200);
      }
      await sleep(150);
    }
    throw new Error(`${this.who}: timed out waiting for ${expression}${last ? ` (${last.message})` : ""}`);
  }
  async settle(ms = 700) { await this.waitFor("window.__hg && __hg.idle()"); await sleep(ms); }
  async goto(route) {
    await this.send("Page.bringToFront"); // a background tab can neither be screenshotted nor render reliably
    this.route = null;
    await this.send("Page.navigate", { url: BASE + route });
    await sleep(400);
    await this.settle();
    this.route = route;
    await this.eval("window.scrollTo(0, 0); true");
  }
  // targets: name -> JS expression giving an element or an [x, y, w, h] rectangle in CSS pixels.
  async shot(id, targets) {
    await sleep(250);
    const rects = {};
    for (const [name, expr] of Object.entries(targets)) {
      const r = await this.eval(`(() => { const t = (${expr}); if (!t) return null; return Array.isArray(t) ? t : __hg.rect(t); })()`);
      if (r && r[2] > 0 && r[3] > 0) rects[name] = r.map((v) => Math.round(v * DPR));
      else console.warn(`  [warn] ${id}: target "${name}" not found`);
    }
    const { data } = await this.send("Page.captureScreenshot", { format: "png", fromSurface: true });
    writeFileSync(path.join(OUT, `${id}.png`), Buffer.from(data, "base64"));
    manifest[id] = { file: `shots/${id}.png`, w: W * DPR, h: H * DPR, who: this.who, targets: rects };
    console.log(`  [ok] ${id}: ${Object.keys(rects).join(", ") || "(no targets)"}`);
  }
}

async function signIn(cdp, email) {
  const password = ACCOUNTS[email];
  if (!password) throw new Error(`no password for ${email} in the accounts file`);
  const { sessionId } = await newTab(cdp);
  const page = new Page(cdp, sessionId, email);
  page.targetId = (await cdp.send("Target.getTargetInfo", {}, sessionId)).targetInfo.targetId;
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DPR, mobile: false });
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }, { name: "prefers-reduced-motion", value: "reduce" }] });
  await page.send("Page.addScriptToEvaluateOnNewDocument", { source: HELPERS });
  await page.send("Page.navigate", { url: `${BASE}/` });
  await page.waitFor(`!!document.querySelector("input[type=email]")`);
  await page.eval(`__hg.set(__hg.q("input[type=email]"), ${JSON.stringify(email)}); __hg.set(__hg.q("input[type=password]"), ${JSON.stringify(password)}); __hg.q("form.login-card").requestSubmit(); true`);
  await page.waitFor(`!document.querySelector("form.login-card") && !!document.querySelector(".sidebar")`, 30000);
  await page.settle();
  console.log(`signed in: ${email}`);
  return page;
}

const JOB = "/candidates?job=JOB-DATA-01";
const RANKING = `__hg.q("section[aria-label=Ranking]")`;
const row = (id) => `__hg.find("section[aria-label=Ranking] tbody tr", ${JSON.stringify(id)})`;
const REVIEWER = `(() => { const h = __hg.findLast("h2.section-title", "High-risk items"); return h && h.nextElementSibling; })()`;
const KARIM_CARD = `__hg.find(".card h3", "Karim Mansour").closest(".card")`;

async function shortlist(page, k) {
  await page.eval(`__hg.set(__hg.q("section[aria-label=Ranking] input[type=number]"), ${k}); true`);
  await sleep(600);
  await page.settle(900);
}

async function pickRow(page, id) {
  await page.eval(`${row(id)}.click(); true`);
  await page.waitFor(`(__hg.q(".detail-pane h2")?.parentElement?.innerText || "").includes(${JSON.stringify(id)})`);
  await page.settle();
}

// The high-risk reviewer shows one item at a time: step through it until the item mentions `needle`.
async function showHighRisk(page, needle) {
  for (let i = 0; i < 30; i++) {
    if (await page.eval(`(${REVIEWER}?.innerText || "").includes(${JSON.stringify(needle)})`)) return;
    const moved = await page.eval(`(() => { const b = [...(${REVIEWER}?.querySelectorAll("button") ?? [])].find((x) => x.innerText.includes("Next")); if (!b || b.disabled) return false; b.click(); return true; })()`);
    if (!moved) break;
    await sleep(300);
  }
  throw new Error(`${page.who}: no high-risk item mentioning ${needle}`);
}

// Each step makes one or more shots, in demo order. Data-changing steps come last.
const STEPS = [
  ["overview", async ({ karim }) => {
    const p = await karim();
    await p.goto("/overview");
    await p.waitFor(`!!__hg.q(".model-card.is-ready, .model-card.is-down, .model-card.is-warming")`, 60000);
    await p.shot("overview", {
      tiles: `__hg.q(".overview-tiles")`, model: `__hg.q(".model-card")`,
      sidebar: `__hg.union(__hg.q("section.nav-group[aria-label='HireGuard']"), __hg.q("section.nav-group[aria-label='HR Nexus']"))`,
    });
  }],
  ["cand_top,cand_justif,cand_evidence", async ({ nour }) => {
    const p = await nour();
    await p.goto(JOB);
    await p.waitFor(`!!${row("CAND-")}`);
    const top = await p.eval(`__hg.q("section[aria-label=Ranking] tbody tr .muted.small").innerText.trim()`);
    await p.goto(`${JOB}&c=${top}`);
    await p.waitFor(`!!__hg.q(".detail-pane .score-big")`);
    await p.settle();
    await p.eval(`__hg.top(${RANKING}); true`);
    await p.shot("cand_top", { ranking: RANKING, score: `__hg.q(".detail-pane .score-col")`, note: `__hg.q(".detail-pane p[role=note]")` });
    await p.eval(`(() => { const c = __hg.all(".detail-pane .component").find((e) => e.querySelector("strong.cap")?.innerText.trim().toLowerCase() === "skills"); window.__justif = c.querySelector(".justifications button"); window.__comp = c; __hg.center(c); return true; })()`);
    await p.shot("cand_justif", { justif: `window.__justif`, component: `window.__comp` });
    await p.eval(`window.__justif.click(); true`);
    await sleep(1600);
    await p.shot("cand_evidence", { mark: `__hg.q(".evidence-text mark")`, evidence: `__hg.q(".evidence-text mark").closest(".card")` });
  }],
  ["cand_skills", async ({ nour }) => {
    const p = await nour();
    await p.goto(`${JOB}&c=CAND-003`); // Sarah Haddad: one skill only listed, the others backed by dated jobs
    await p.waitFor(`!!__hg.q(".detail-pane .score-big")`);
    await p.settle();
    await p.eval(`__hg.top(__hg.q(".detail-pane .card")); true`);
    await p.shot("cand_skills", {
      skills: `__hg.find(".detail-pane .section-gap", "Validated skills")`,
      note: `__hg.union(__hg.q(".detail-pane p[role=note]"), __hg.q(".detail-pane .score-col"))`,
      listed: `__hg.find(".detail-pane .skill", "listed only")`,
    });
  }],
  ["poison_alert", async ({ nour }) => {
    const p = await nour();
    await p.goto(`${JOB}&c=CAND-006`);
    await p.waitFor(`!!__hg.q(".detail-pane .alert.danger") && !!${row("CAND-006")} && !!__hg.q(".detail-pane .score-col")`, 45000);
    await p.settle();
    await p.eval(`__hg.top(${RANKING}); true`);
    await p.shot("poison_alert", { row: row("CAND-006"), alert: `__hg.q(".detail-pane .alert.danger")`, score: `__hg.q(".detail-pane .score-col")` });
  }],
  ["poison_reveal", async ({ karim }) => {
    const p = await karim();
    await p.goto("/security");
    await p.waitFor(`!!__hg.find(".card h3", "Karim Mansour")`, 60000);
    await p.eval(`__hg.top(${KARIM_CARD}); true`);
    await p.shot("poison_reveal", { card: KARIM_CARD, hidden: `__hg.union(...__hg.all(".finding", ${KARIM_CARD}).slice(0, 2))` });
  }],
  ["twins", async ({ nour }) => {
    const p = await nour();
    await p.goto(JOB);
    await shortlist(p, 2);
    await p.waitFor(`!!__hg.deep("section[aria-label=Ranking] span", "borderline")`, 15000);
    await p.eval(`__hg.center(${row("CAND-002")}); true`);
    await p.shot("twins", { twins: `__hg.union(${row("CAND-002")}, ${row("CAND-008")})`, ranking: RANKING });
  }],
  ["team_rubric", async ({ karim }) => {
    const p = await karim();
    await p.goto(JOB);
    await p.waitFor(`!!__hg.find(".card h3", "Team-aware rubric")`);
    await p.eval(`__hg.top(__hg.find(".card h3", "Team-aware rubric").closest(".card")); true`);
    await p.shot("team_rubric", { card: `__hg.find(".card h3", "Team-aware rubric").closest(".card")`, spark: `__hg.find(".card li", "Apache Spark")` });
  }],
  ["offer_band,offer_fit", async ({ karim }) => {
    const p = await karim();
    await p.goto(JOB);
    await shortlist(p, 2);
    await pickRow(p, "CAND-002");
    await p.eval(`window.scrollTo(0, 0); true`);
    await p.shot("offer_band", { band: `__hg.deep("span, div", "band covers").closest(".card")` });
    await p.eval(`__hg.center(__hg.find(".detail-pane .card h3", "Offer fit").closest(".card")); true`);
    await p.shot("offer_fit", {
      fit: `__hg.find(".detail-pane .card h3", "Offer fit").closest(".card")`,
      mismatch: `__hg.find(".detail-pane .card li", "mismatch")`,
    });
  }],
  ["inbox", async ({ karim }) => {
    const p = await karim();
    await p.goto("/inbox");
    await p.waitFor(`!!__hg.q(".lanes")`);
    await p.eval(`__hg.top(__hg.q(".lanes")); true`);
    await p.shot("inbox", { lanes: `__hg.q(".lanes")`, spoof: `__hg.q(".lane-suspicious")` });
  }],
  ["approvals,approvals_more", async ({ karim }) => {
    const p = await karim();
    await p.goto("/approvals");
    await p.eval(`__hg.top(__hg.findLast("h2.section-title", "High-risk items"), 330); true`);
    await p.shot("approvals", {
      queue: `__hg.union(__hg.deep("div", "Routine items in batches")?.closest(".tile, .card, a, div"), __hg.findLast("h2.section-title", "High-risk items"))`,
      guard: `__hg.deep("div", "Attention guard")`,
    });
    await p.eval(`(() => { const h = __hg.deep("h2, h3", "Silent candidates"); __hg.top(h ? (h.closest(".card") || h) : __hg.findLast("h2.section-title", "Routine batches")); return true; })()`);
    await p.shot("approvals_more", {
      followups: `(() => { const h = __hg.deep("h2, h3", "Silent candidates"); return h && (h.closest(".card") || h); })()`,
      interviews: `__hg.union(...__hg.all("tr").filter((r) => /Interview CAND-/.test(r.innerText) && r.getBoundingClientRect().top > 70 && r.getBoundingClientRect().bottom < 860))`,
    });
  }],
  ["team_skills,team_process,team_gaps", async ({ karim }) => {
    const p = await karim();
    await p.goto("/team");
    await p.waitFor(`!!__hg.find("tr", "Spark")`);
    await p.shot("team_skills", { spark: `__hg.find("tr", "Spark")`, card: `__hg.find("tr", "Spark").closest(".card")` });
    await p.eval(`__hg.find(".seg button", "HR process").click(); true`);
    await p.settle(900);
    // A fresh demo database has no hiring history yet: show the panel's own labelled simulation.
    await p.eval(`__hg.find("button", "Simulation")?.click(); true`);
    await p.settle(900);
    await p.shot("team_process", { steps: `__hg.deep(".card, section", "Median days per step")` });
    await p.eval(`__hg.find(".seg button", "Knowledge gaps").click(); true`);
    await p.waitFor(`!!__hg.find(".card h3", "Questions per handbook section") && !!__hg.find(".hbar-row", "Remote work")`, 45000);
    await p.settle(900);
    await p.shot("team_gaps", {
      sections: `__hg.find(".card h3", "Questions per handbook section").closest(".card")`,
      hidden: `__hg.union(...__hg.all(".hbar-row").filter((r) => r.innerText.includes("hidden")))`,
      remote: `__hg.find(".hbar-row", "Remote work")`,
    });
  }],
  ["money", async ({ karim }) => {
    const p = await karim();
    await p.goto("/money");
    await p.shot("money", { hours: `__hg.deep(".card", "Hours saved")` });
  }],
  ["test_results,fairness", async ({ karim }) => {
    const p = await karim();
    await p.goto("/security");
    await p.eval(`__hg.find("[role=tab]", "Test results").click(); true`);
    await p.settle(1200);
    await p.eval(`(() => { const h = __hg.deep("h2, h3", "Can hidden text change a score"); if (h) __hg.top(h); return true; })()`);
    await p.shot("test_results", { attacks: `(() => { const h = __hg.deep("h2, h3", "Can hidden text change a score"); return h && (h.closest(".card") || h); })()` });
    await p.eval(`__hg.find("[role=tab]", "Fairness check").click(); true`);
    await p.settle(1200);
    await p.eval(`(() => { const h = __hg.deep("h2, h3, h4, strong", "Does the check actually work"); if (h) __hg.center(h.closest(".card") || h); return true; })()`);
    await p.shot("fairness", { works: `(() => { const h = __hg.deep("h2, h3, h4, strong", "Does the check actually work"); return h && (h.closest(".card") || h); })()` });
  }],
  // ---------------------------------------------------------------- these change data, in demo order
  ["offer_form,offer_sent", async ({ karim }) => {
    const p = await karim();
    await p.goto(JOB);
    await shortlist(p, 2);
    await pickRow(p, "CAND-008");
    await p.eval(`(() => { const d = __hg.find(".detail-pane details", "Draft offer letter"); d.open = true; __hg.set(d.querySelector("input[type=number]"), 3300); __hg.top(__hg.find(".detail-pane .card h3", "Offer fit").closest(".card")); return true; })()`);
    await sleep(400);
    await p.shot("offer_form", { form: `__hg.find(".detail-pane details", "Draft offer letter")`, send: `__hg.find(".detail-pane details button", "Send to approval")` });
    await p.eval(`__hg.find(".detail-pane details button", "Send to approval").click(); true`);
    await p.waitFor(`!!__hg.find(".alert", "drafted")`);
    await p.eval(`window.scrollTo(0, 0); true`);
    await p.shot("offer_sent", { notice: `__hg.find(".alert", "drafted")` });
  }],
  ["approve_second", async ({ leila }) => {
    const p = await leila();
    await p.goto("/approvals");
    await showHighRisk(p, "CAND-008");
    await p.eval(`(() => { const b = [...${REVIEWER}.querySelectorAll("button")].find((x) => x.innerText.trim() === "Approve"); b.click(); return true; })()`);
    await p.waitFor(`!!__hg.find(".alert", "approval is recorded")`);
    await p.settle();
    await p.eval(`__hg.top(__hg.find(".alert", "approval is recorded"), 20); true`);
    await p.shot("approve_second", { item: REVIEWER, waiting: `__hg.find(".alert.warn", "needs")`, msg: `__hg.find(".alert", "approval is recorded")` });
  }],
  // The recruiter never sees offers (HR managers only), so the refused run is the offer's own author.
  ["refused_before,refused_403", async ({ karim }) => {
    const p = await karim();
    await p.goto("/approvals");
    await showHighRisk(p, "CAND-008");
    await p.eval(`__hg.center(__hg.find("button", "Execute without approval")); true`);
    await p.shot("refused_before", { item: REVIEWER, button: `__hg.find("button", "Execute without approval")` });
    await p.eval(`__hg.find("button", "Execute without approval").click(); true`);
    await p.waitFor(`!!__hg.find(".alert", "403")`);
    await p.eval(`__hg.top(__hg.find(".alert", "403")); true`);
    await p.shot("refused_403", { error: `__hg.find(".alert", "403")`, item: REVIEWER });
  }],
  ["audit_refused", async ({ karim }) => {
    const p = await karim();
    await p.goto("/security");
    await p.eval(`__hg.find("[role=tab]", "Activity record").click(); true`);
    await p.settle(1200);
    await p.waitFor(`!!__hg.find("tr", "Action refused")`, 15000);
    await p.eval(`__hg.center(__hg.find("tr", "Action refused")); true`);
    await p.shot("audit_refused", { refused: `__hg.find("tr", "Action refused")`, table: `__hg.find("tr", "Action refused").closest("table")` });
  }],
  ["answer_extract,answer_routed", async ({ employee }) => {
    const p = await employee();
    await p.goto("/answer-desk");
    const ask = async (q) => {
      await p.eval(`__hg.set(__hg.q("form textarea"), ${JSON.stringify(q)}); __hg.q("form textarea").closest("form").requestSubmit(); true`);
      await p.waitFor(`!!__hg.q(".extract") || !!__hg.deep("p, div", "ticket")`, 30000);
      await p.settle(900);
    };
    await ask("Combien de jours de congé annuel ?");
    await p.eval(`__hg.top(__hg.q("form textarea").closest("form")); true`);
    await p.shot("answer_extract", { extract: `__hg.q(".extract")`, question: `__hg.q("form textarea")` });
    await ask("Quel est mon solde de congés ?");
    await p.shot("answer_routed", { routed: `__hg.deep("p, div", "ticket")`, question: `__hg.q("form textarea")` });
  }],
  ["documents", async ({ employee }) => {
    const p = await employee();
    await p.goto("/documents");
    await p.eval(`__hg.find("form button", "Request").click(); true`);
    await p.waitFor(`!!__hg.find(".alert", "Request sent")`);
    await p.settle();
    await p.eval(`__hg.center(__hg.find(".alert", "Request sent")); true`);
    await p.shot("documents", {
      request: `__hg.union(__hg.find(".alert", "Request sent"), __hg.find("h2", "Request a document")?.closest(".card"))`,
      notice: `__hg.find(".alert", "Request sent")`,
    });
  }],
];

async function main() {
  mkdirSync(OUT, { recursive: true });
  const { cdp, close } = await launch();
  const pages = {};
  // One tab at a time: a tab left in the background stops rendering reliably in headless Chrome, so switching user
  // closes the previous tab and signs in again.
  let current = null;
  const user = (email) => async () => {
    if (current?.who === email) return current;
    if (current) await cdp.send("Target.closeTarget", { targetId: current.targetId }).catch(() => {});
    current = pages[email] = await signIn(cdp, email);
    return current;
  };
  const users = {
    nour: user("recruiter@hireguard.demo"), karim: user("hrm@hireguard.demo"),
    leila: user("hrm2@hireguard.demo"), employee: user("employee@hireguard.demo"),
  };
  try {
    for (const [ids, run] of STEPS) {
      if (!ONLY || ids.split(",").some((id) => ONLY.includes(id))) await run(users);
    }
  } finally {
    writeFileSync(MANIFEST, JSON.stringify(manifest, null, 1));
    close();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

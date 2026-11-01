// Records the backup demo video: the click path of docs/demo_script.md, step by step, in one browser tab.
// Run through record.ps1 (fresh database, seed, servers); alone it needs a running app and work/passwords.json.
//
//   HG_DEMO_URL        app URL (default http://127.0.0.1:5180, the port record.ps1 starts Vite on)
//   HG_DEMO_PASSWORDS  JSON {email: password} written by record.ps1 from the seed output
//   HG_DEMO_PACE       pause multiplier: 1 = about 2.5 minutes, 0.3 for a quick selector check
//   HG_DEMO_HEADED=1   show the browser while recording
//
// Every "Must be visible" item of the script is checked; out/report.md lists each check, the model status and
// the twin scores. A failed check does not stop the recording, but the exit code is 1.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "out");
const BASE = (process.env.HG_DEMO_URL ?? "http://127.0.0.1:5180").replace(/\/+$/, "");
const PASSWORDS = JSON.parse(fs.readFileSync(process.env.HG_DEMO_PASSWORDS ?? path.join(HERE, "work", "passwords.json"), "utf8"));
const PACE = Number(process.env.HG_DEMO_PACE ?? 1);
const JOB = "JOB-DATA-01";

const USERS = {
  nour: { email: "recruiter@hireguard.demo", who: "Nour, recruiter" },
  karim: { email: "hrm@hireguard.demo", who: "Karim, HR manager" },
  leila: { email: "hrm2@hireguard.demo", who: "Leila, second HR manager" },
};

const checks = []; // { step, what, ok, detail }
const facts = {}; // values worth reading in the report (model status, twin scores)

fs.mkdirSync(path.join(OUT, "steps"), { recursive: true });

async function launch() {
  const headless = process.env.HG_DEMO_HEADED !== "1";
  for (const channel of ["msedge", "chrome", undefined]) {
    try {
      return await chromium.launch({ channel, headless });
    } catch {
      /* next browser */
    }
  }
  throw new Error("No browser found: install Edge or Chrome, or run `npx playwright install chromium`.");
}

const browser = await launch();
const size = { width: 1440, height: 900 };
const ctx = await browser.newContext({ viewport: size, recordVideo: { dir: path.join(OUT, "raw"), size } });
const page = await ctx.newPage();
const hold = (ms) => page.waitForTimeout(Math.round(ms * PACE));

/** The caption bar at the bottom of every frame: step, who is signed in, and the line to say. */
async function caption(step, who, text) {
  await page.evaluate(
    ([step, who, text]) => {
      let bar = document.getElementById("hg-demo-caption");
      if (!bar) {
        bar = document.createElement("div");
        bar.id = "hg-demo-caption";
        Object.assign(bar.style, {
          position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "2147483647", padding: "14px 28px",
          background: "rgba(17, 24, 39, 0.92)", color: "#fff", font: "500 20px/1.4 system-ui, sans-serif",
          pointerEvents: "none", display: "flex", gap: "18px", alignItems: "baseline",
        });
        document.body.appendChild(bar);
      }
      bar.replaceChildren();
      const tag = document.createElement("span");
      tag.textContent = step;
      Object.assign(tag.style, { color: "#93c5fd", fontWeight: "700", whiteSpace: "nowrap" });
      const line = document.createElement("span");
      line.textContent = text;
      const user = document.createElement("span");
      user.textContent = who;
      Object.assign(user.style, { marginLeft: "auto", color: "#cbd5e1", fontSize: "15px", whiteSpace: "nowrap" });
      bar.append(tag, line, user);
    },
    [step, who, text],
  );
}

/** Headless video shows no mouse: outline the element before clicking it. */
async function show(locator) {
  const el = locator.first();
  await el.scrollIntoViewIfNeeded();
  await el.evaluate((n) => {
    n.style.outline = "3px solid #f59e0b";
    n.style.outlineOffset = "2px";
  });
  await hold(700);
  return el;
}
async function click(locator) {
  const el = await show(locator);
  await el.click();
  await el.evaluate((n) => (n.style.outline = "")).catch(() => {});
}

async function check(step, what, locator, timeout = 15000) {
  try {
    await locator.first().waitFor({ state: "visible", timeout });
    checks.push({ step, what, ok: true });
    return true;
  } catch (e) {
    const shot = `steps/${step}-fail-${checks.length}.png`;
    await page.screenshot({ path: path.join(OUT, shot) }).catch(() => {});
    checks.push({ step, what, ok: false, detail: `not visible after ${timeout / 1000} s (${shot})` });
    console.error(`[${step}] FAILED: ${what}`);
    return false;
  }
}

async function snap(step) {
  await page.screenshot({ path: path.join(OUT, "steps", `${step}.png`) }).catch(() => {});
}

let current = null;
async function signIn(key) {
  const u = USERS[key];
  if (current === key) return u.who;
  if (current) {
    await click(page.getByRole("button", { name: "Log out" }));
  } else {
    await page.goto(BASE);
  }
  await page.getByLabel("Email").waitFor();
  await caption("", u.who, `Signing in as ${u.who}`);
  await page.getByLabel("Email").fill(u.email);
  await page.getByLabel("Password").fill(PASSWORDS[u.email] ?? "");
  await click(page.getByRole("button", { name: "Sign in" }));
  await page.getByRole("button", { name: "Log out" }).waitFor({ timeout: 20000 });
  current = key;
  return u.who;
}

async function go(route) {
  await page.goto(BASE + route);
  await page.getByRole("button", { name: "Log out" }).waitFor({ timeout: 20000 });
}

const row = (id) => page.locator("tr.clickable", { hasText: id });

try {
  // ------------------------------------------------------------ title card
  await page.goto(BASE);
  await caption("HireGuard", "", "Backup demo, recorded " + new Date().toISOString().slice(0, 10) + ". All people, CVs and emails are fictional.");
  await hold(3000);

  // ------------------------------------------------------------ 1. ranking with evidence
  let who = await signIn("nour");
  const status = await page.request.get(BASE + "/api/model/status?refresh=1").then((r) => r.json()).catch((e) => ({ error: String(e) }));
  facts["Model status (GET /api/model/status)"] = "`" + JSON.stringify(status) + "`";
  await go(`/candidates?job=${JOB}`);
  await caption("1", who, "Code ranks from validated fields only; each line points to the evidence. The score is proposed.");
  await check("1", "ranking loaded", page.locator("tr.clickable"));
  const offline = await page.getByText("offline extraction").count();
  facts["Candidates with the \"offline extraction\" badge"] = offline
    ? `${offline}: these CVs were NOT read by the model. Re-record with the model up, or say so over the video.`
    : "0: every CV was read by the model";
  await click(page.locator("tr.clickable").first());
  await check("1", "score is labelled proposed", page.getByText("proposed", { exact: false }));
  await click(page.locator(".justifications button.link"));
  await check("1", "highlighted evidence in the CV", page.locator(".evidence-text mark"));
  await hold(3500);
  await snap("1");

  // ------------------------------------------------------------ 2. hidden text
  await caption("2", who, "Hidden white and tiny text was removed before the model read the CV, and flagged for HR. Flags never change a score.");
  await click(row("CAND-006"));
  await check("2", "hidden-text findings on CAND-006", page.getByText("were found and removed before the model read the CV"));
  await show(page.locator(".alert.danger"));
  await hold(4000);
  await snap("2");

  // ------------------------------------------------------------ 3. twins and borderline
  await caption("3", who, "Same CV, other town. Any ranker picks one by sort order; we flag it as borderline and leave it to a human.");
  const k = page.locator("input[type=number]").first();
  await show(k);
  await k.fill("2");
  await hold(1500);
  for (const id of ["CAND-002", "CAND-008"]) {
    const ok = await check("3", `${id} badged borderline`, row(id).getByText("borderline"));
    const score = (await row(id).locator("td.num").textContent().catch(() => "")) ?? "";
    facts[`${id} score`] = score.trim() || "(not found)";
    if (ok) await show(row(id));
  }
  await hold(3500);
  await snap("3");

  // ------------------------------------------------------------ 4. offer fit and two approvals
  who = await signIn("karim");
  await go(`/candidates?job=${JOB}`);
  await caption("4", who, "We found the deal-breaker before the interview. We don't predict who accepts: we ask, and check against the published band.");
  await check("4", "\"band covers\" badge", page.getByText("band covers"));
  await show(page.getByText("band covers"));
  await hold(2000);
  await check("4", "CAND-002 offer mismatch", row("CAND-002").getByText("offer mismatch"));
  await show(row("CAND-002").getByText("offer mismatch"));
  await hold(2000);
  await click(row("CAND-008"));
  await click(page.getByText("Draft offer letter"));
  const salary = page.getByLabel("Gross salary (TND / month)");
  await show(salary);
  await salary.fill("3300");
  await click(page.getByRole("button", { name: "Send to approval" }));
  await check("4", "offer drafted for CAND-008", page.getByText("Offer for CAND-008 drafted"));
  await hold(2500);

  who = await signIn("leila");
  await go("/approvals");
  await caption("4", who, "The offer waits for two HR managers other than its author. Nobody can release it alone.");
  const card = page.locator(".card.high-risk");
  await check("4", "high-risk reviewer shown", card);
  for (let i = 0; i < 30; i++) {
    const meta = (await card.locator(".muted.small").nth(1).textContent().catch(() => "")) ?? "";
    const title = (await card.locator("h3").textContent().catch(() => "")) ?? "";
    if (meta.startsWith("Offers") && /CAND-008|Youssef/.test(title + meta)) break;
    const next = card.getByRole("button", { name: "Next →" });
    if (await next.isDisabled()) break;
    await next.click();
    await hold(150);
  }
  await click(card.getByRole("button", { name: "Approve", exact: true }));
  await check("4", "offer pending: a second HR manager must approve", page.getByText("A second HR manager must approve"));
  await show(page.getByText("A second HR manager must approve"));
  await hold(3000);
  await caption("4", who, "Waiting is the control working. A one-HR-manager SME sets this rule to 1; the change is audited.");
  await check("4", "offer approval rule card", page.locator("#offer-rule"));
  await show(page.locator(".offer-rule"));
  await hold(3500);
  await snap("4");

  // ------------------------------------------------------------ 5. executor refuses
  who = await signIn("nour");
  await go("/approvals");
  await caption("5", who, "Run something nobody approved: the executor refuses with 403, and the refusal is in the audit log.");
  const execute = page.getByRole("button", { name: "Execute without approval" });
  if (await check("5", "an \"Execute without approval\" button", execute)) {
    await click(execute);
    await check("5", "red 403 Forbidden", page.getByText("403 Forbidden"));
    await show(page.getByText("403 Forbidden"));
  }
  await hold(4000);
  await snap("5");

  // ------------------------------------------------------------ 6. HR Nexus
  who = await signIn("karim");
  await go("/team");
  await caption("6", who, "HR Nexus: the data team has nobody with Spark. We measure the process and the handbook, never the people.");
  await click(page.getByRole("button", { name: "Skills map" }));
  await check("6", "Apache Spark gap", page.getByText("Apache Spark"));
  await show(page.getByText("Apache Spark"));
  await hold(3500);
  await click(page.getByRole("button", { name: "Knowledge gaps" }));
  await caption("6", who, "Employees ask most about remote work (fictional demo log). Cells under 5 people are hidden.");
  await check("6", "Remote work on top", page.getByText(/remote work/i));
  await hold(4000);
  await snap("6");

  // ------------------------------------------------------------ 7. where the numbers come from
  await go("/security");
  await click(page.getByRole("tab", { name: /evaluation/i }));
  await caption("7", who, "Every number in the pitch comes from here, labelled with the run that produced it: model or code path.");
  await check("7", "Evaluation tab", page.getByText(/model/i));
  await hold(5000);
  await snap("7");

  await caption("HireGuard", "", "HireGuard does the paperwork; people decide about people.");
  await hold(3000);
} catch (e) {
  checks.push({ step: "-", what: "script ran to the end", ok: false, detail: String(e).split("\n")[0] });
  await page.screenshot({ path: path.join(OUT, "steps", "crash.png") }).catch(() => {});
  console.error(e);
} finally {
  const video = page.video();
  await ctx.close();
  await browser.close();
  const target = path.join(OUT, "hireguard_demo.webm");
  if (video) {
    fs.rmSync(target, { force: true });
    fs.renameSync(await video.path(), target);
    fs.rmSync(path.join(OUT, "raw"), { recursive: true, force: true });
  }
  const failed = checks.filter((c) => !c.ok).length;
  const lines = [
    "# Demo video report",
    "",
    `Recorded ${new Date().toISOString()} against ${BASE}, pace ${PACE}. Video: \`demo_video/out/hireguard_demo.webm\` (not committed).`,
    "",
    `**${checks.length - failed}/${checks.length} checks passed.**`,
    "",
    "| Step | Must be visible | Result |",
    "|---|---|---|",
    ...checks.map((c) => `| ${c.step} | ${c.what} | ${c.ok ? "ok" : "**FAIL** " + (c.detail ?? "")} |`),
    "",
    "## Facts read during the run",
    "",
    ...Object.entries(facts).map(([k, v]) => `- ${k}: ${v}`),
    "",
  ];
  fs.writeFileSync(path.join(OUT, "report.md"), lines.join("\n"));
  console.log(lines.join("\n"));
  process.exitCode = failed ? 1 : 0;
}

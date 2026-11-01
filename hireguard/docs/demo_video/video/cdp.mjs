// Minimal Chrome DevTools protocol client for capture.mjs and render.mjs (Node 22+: built-in WebSocket and fetch).
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0;
    this.pending = new Map();
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej, method } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? rej(new Error(`${method}: ${msg.error.message}`)) : res(msg.result);
      }
    };
  }
  open() { return new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; }); }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej, method }));
  }
}

function findBrowser() {
  const candidates = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
  ];
  const found = candidates.find((c) => existsSync(c));
  if (!found) throw new Error("Chrome or Edge not found");
  return found;
}

/** Headless Chrome on a throwaway profile. Returns the protocol client and a close function. */
export async function launch(extra = []) {
  const profile = mkdtempSync(path.join(tmpdir(), "hg-chrome-"));
  const port = 9300 + Math.floor(Math.random() * 500);
  const proc = spawn(findBrowser(), [
    "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars", "--force-color-profile=srgb",
    "--lang=en-US", "--window-size=1920,1080", ...extra, "about:blank",
  ], { stdio: "ignore" });
  let ws;
  for (let i = 0; i < 80 && !ws; i++) {
    await sleep(150);
    try { ws = (await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl; } catch {}
  }
  if (!ws) throw new Error("Chrome did not start");
  const cdp = new CDP(ws);
  await cdp.open();
  return { cdp, close: () => { proc.kill(); setTimeout(() => rmSync(profile, { recursive: true, force: true }), 1500); } };
}

/** A new tab in its own browser context (separate cookies), attached with a flat session. */
export async function newTab(cdp) {
  const { browserContextId } = await cdp.send("Target.createBrowserContext", { disposeOnDetach: true });
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank", browserContextId });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  return { sessionId, send: (method, params) => cdp.send(method, params, sessionId) };
}

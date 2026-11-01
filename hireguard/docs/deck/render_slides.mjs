// Renders the pitch deck (project/deck.json + project/slides/*.html, the files of the Slides artifact) to one
// 1920x1080 JPEG per slide, plus slides.json (order, section, title, speaker notes, video) for build_pptx.mjs.
//
//   node render_slides.mjs [--out build]
//
// The slide format is a closed HTML/CSS subset (inline styles, flex/grid, pinned boxes), so Chrome draws it as the
// deck does once the subset's defaults are set; <x-connector> arrows are drawn here as SVG. Uploaded images
// (/_blob/<id>) map to repo files through blobs.json.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { launch, newTab, sleep } from "../demo_video/video/cdp.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const OUT = path.resolve(arg("out", path.join(HERE, "build")));
mkdirSync(OUT, { recursive: true });

const deck = JSON.parse(readFileSync(path.join(HERE, "project", "deck.json"), "utf8"));
const blobs = JSON.parse(readFileSync(path.join(HERE, "blobs.json"), "utf8"));
const blobUrl = (id) => {
  if (!blobs[id]) throw new Error(`blobs.json has no file for /_blob/${id}`);
  return pathToFileURL(path.resolve(HERE, blobs[id])).href;
};
const fonts = Object.values(deck.faces).map((f) => `<link rel="stylesheet" href="${f.href}">`).join("\n");
const sectionOf = {};
for (const s of Object.values(deck.sections)) sectionOf[s.start] = s.description;

// The subset's defaults: no margins, h1-h3/p sizes, a box without display is a column (an inline display:flex
// keeps CSS's row default), notes hidden.
const BASE = `<style>
html, body { margin: 0; background: #000; }
section { position: relative; width: 1920px; height: 1080px; overflow: hidden; }
section:not([style*="display"]), div:not([style*="display"]) { display: flex; flex-direction: column; }
section, section * { box-sizing: border-box; }
h1, h2, h3, p, ul, ol { margin: 0; }
h1 { font-size: 96px; font-weight: 600; line-height: 1.1; }
h2 { font-size: 64px; font-weight: 600; line-height: 1.15; }
h3 { font-size: 44px; font-weight: 600; line-height: 1.2; }
p, li { font-size: 32px; line-height: 1.4; }
img, svg { display: block; flex: none; }
aside { display: none; }
</style>`;

// <x-connector x1 y1 x2 y2 head="end|both|none"> -> an SVG line with filled heads, in its host's coordinates.
const CONNECTORS = `
for (const c of [...document.querySelectorAll("x-connector")]) {
  const host = c.parentElement.closest('div[style*="position:relative"]') || document.querySelector("section");
  const cs = c.getAttribute("style") || "";
  const color = (cs.match(/(?:^|;)\\s*color:\\s*([^;]+)/) || [])[1] || "#0E1525";
  const w = parseFloat((cs.match(/border-width:\\s*([\\d.]+)/) || [])[1] || "2");
  const dashed = /border-style:\\s*(dashed|dotted)/.exec(cs);
  const n = (k) => parseFloat(c.getAttribute(k));
  const [x1, y1, x2, y2] = ["x1", "y1", "x2", "y2"].map(n);
  const head = c.getAttribute("head") || "end";
  const hl = 6 + 3.2 * w, hw = 4 + 2.4 * w;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const tip = (x, y, a) => {
    const bx = x - hl * Math.cos(a), by = y - hl * Math.sin(a);
    const px = -Math.sin(a) * hw, py = Math.cos(a) * hw;
    return \`<path d="M\${x} \${y} L\${bx + px} \${by + py} L\${bx - px} \${by - py} Z" fill="\${color}"/>\`;
  };
  const endIn = head === "end" || head === "both" ? hl * 0.8 : 0, startIn = head === "both" ? hl * 0.8 : 0;
  const lx1 = x1 + startIn * Math.cos(ang), ly1 = y1 + startIn * Math.sin(ang);
  const lx2 = x2 - endIn * Math.cos(ang), ly2 = y2 - endIn * Math.sin(ang);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", host.offsetWidth); svg.setAttribute("height", host.offsetHeight);
  svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible;pointer-events:none";
  svg.innerHTML = \`<line x1="\${lx1}" y1="\${ly1}" x2="\${lx2}" y2="\${ly2}" stroke="\${color}" stroke-width="\${w}"
    \${dashed ? \`stroke-dasharray="\${w * 3} \${w * 2}"\` : ""}/>\`
    + (endIn ? tip(x2, y2, ang) : "") + (startIn ? tip(x1, y1, ang + Math.PI) : "");
  c.replaceWith(svg);
}`;

const { cdp, close } = await launch();
const slides = [];
try {
  const tab = await newTab(cdp);
  await tab.send("Page.enable");
  await tab.send("Runtime.enable");
  await tab.send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const evaluate = async (expression) => {
    const r = await tab.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  for (const [i, id] of deck.order.entries()) {
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) throw new Error(`bad slide id ${id}`);
    let html = readFileSync(path.join(HERE, "project", "slides", `${id}.html`), "utf8");
    html = html.replace(/\/?_blob\/([0-9a-f]{32})/g, (_, b) => blobUrl(b));
    const page = path.join(OUT, `_${id}.html`);
    writeFileSync(page, `<!doctype html><html><head><meta charset="utf-8">${fonts}${BASE}</head><body>${html}</body></html>`);
    await tab.send("Page.navigate", { url: pathToFileURL(page).href });
    for (let k = 0; k < 100 && (await evaluate("document.readyState").catch(() => "")) !== "complete"; k++) await sleep(50);
    await evaluate("document.fonts.ready.then(() => true)");
    await evaluate(`(() => { ${CONNECTORS} })()`);
    await sleep(100);
    const info = await evaluate(`(() => {
      const s = document.querySelector("section");
      const h = s.querySelector("h1, h2");
      const v = s.querySelector("img[data-video]");
      return { title: h ? h.innerText.replace(/\\s+/g, " ").trim() : (v ? v.alt : ""),
               notes: (s.querySelector("aside") || {}).textContent || "",
               video: v ? v.getAttribute("data-video").replace(/^file:\\/\\/\\/?/, "") : null };
    })()`);
    const { data } = await tab.send("Page.captureScreenshot", { format: "jpeg", quality: 93 });
    const file = `${String(i + 1).padStart(2, "0")}_${id}.jpg`;
    writeFileSync(path.join(OUT, file), Buffer.from(data, "base64"));
    slides.push({ id, file, section: sectionOf[id] || null, ...info,
                  video: info.video ? fileURLToPath("file:///" + info.video) : null });
    console.log(`${file}  ${info.title.slice(0, 70)}`);
  }
  writeFileSync(path.join(OUT, "slides.json"), JSON.stringify({ title: deck.title, slides }, null, 2));
} finally {
  close();
}

// Renders the 3-minute demo video: build/timeline.json + screenshots + slides -> frames -> ffmpeg, with the narration.
//
//   node render.mjs --ffmpeg <path to ffmpeg>                 # out/HireGuard_demo_3min.mp4
//   node render.mjs --ffmpeg <path> --from 40 --to 60         # a preview of one part
//   node render.mjs --stills 12.5,47,90                       # PNG frames in build/stills/ for checking
//
// Run voice.py and capture.mjs first. ffmpeg: `pip install imageio-ffmpeg`, then
// python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())".
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { launch, newTab, sleep } from "./cdp.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BUILD = path.join(HERE, "build");
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const PERSONA = {
  "recruiter@hireguard.demo": "Nour, recruiter",
  "hrm@hireguard.demo": "Karim, HR manager",
  "hrm2@hireguard.demo": "Leila, second HR manager",
  "employee@hireguard.demo": "Youssef, employee",
};

const timeline = JSON.parse(readFileSync(path.join(BUILD, "timeline.json"), "utf8"));
const shots = JSON.parse(readFileSync(path.join(BUILD, "shots.json"), "utf8"));
const meta = {}, who = {};
for (const { id } of timeline.shots) {
  if (meta[id]) continue;
  if (id.startsWith("slide:")) {
    const file = path.join(HERE, "..", "slides", `${id.slice(6)}.png`);
    if (!existsSync(file)) throw new Error(`missing slide ${file}: run build_slides.py`);
    meta[id] = { src: pathToFileURL(file).href, w: 1920, h: 1080, targets: {} };
  } else {
    const s = shots[id];
    if (!s) throw new Error(`no screenshot "${id}" in build/shots.json: run capture.mjs`);
    meta[id] = { src: pathToFileURL(path.join(BUILD, s.file)).href, w: s.w, h: s.h, targets: s.targets };
    if (PERSONA[s.who]) who[id] = PERSONA[s.who];
  }
}

const { cdp, close } = await launch();
try {
  const tab = await newTab(cdp);
  await tab.send("Page.enable");
  await tab.send("Runtime.enable");
  await tab.send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await tab.send("Page.navigate", { url: pathToFileURL(path.join(HERE, "stage.html")).href });
  const evaluate = async (expression) => {
    const r = await tab.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  for (let i = 0; i < 100 && !(await evaluate("typeof window.renderAt === 'function'").catch(() => false)); i++) await sleep(100);
  await evaluate(`load(${JSON.stringify(timeline)}, ${JSON.stringify(meta)}, ${JSON.stringify(who)})`);
  const frame = async (t, format = "jpeg") => {
    await evaluate(`renderAt(${t})`);
    // Chrome refuses a screenshot now and then when the machine is short of memory: wait and try again.
    let data;
    for (let attempt = 0; !data; attempt++) {
      try {
        ({ data } = await tab.send("Page.captureScreenshot", { format, ...(format === "jpeg" ? { quality: 93 } : {}), fromSurface: true }));
      } catch (e) {
        if (attempt === 8) throw e;
        await sleep(500 * (attempt + 1));
        await evaluate(`renderAt(${t})`);
      }
    }
    return Buffer.from(data, "base64");
  };

  const stills = arg("stills");
  if (stills) {
    mkdirSync(path.join(BUILD, "stills"), { recursive: true });
    for (const t of stills.split(",").map(Number)) {
      writeFileSync(path.join(BUILD, "stills", `t${t.toFixed(2)}.png`), await frame(t, "png"));
      console.log(`  still at ${t}s`);
    }
  } else {
    const fps = timeline.fps;
    const from = Number(arg("from", 0)), to = Number(arg("to", timeline.duration));
    const out = path.resolve(arg("out", path.join(HERE, "..", "out", from === 0 && to === timeline.duration ? "Venidis_demo_3min.mp4" : `preview_${from}-${to}.mp4`)));
    mkdirSync(path.dirname(out), { recursive: true });
    const ffmpeg = spawn(arg("ffmpeg", "ffmpeg"), [
      "-hide_banner", "-loglevel", "error", "-y",
      "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
      "-ss", String(from), "-t", String(to - from), "-i", path.join(BUILD, "narration.wav"),
      "-map", "0:v", "-map", "1:a",
      // JPEG frames are full-range BT.601; players expect video-range BT.709.
      "-vf", "scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
      "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
      "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", String(fps),
      "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", "-shortest", "-f", "mp4", `${out}.part`,
    ], { stdio: ["pipe", "inherit", "inherit"] });
    const done = new Promise((res, rej) => ffmpeg.on("close", (code) => (code === 0 ? res() : rej(new Error(`ffmpeg exited ${code}`)))));
    const n = Math.round((to - from) * fps), t0 = Date.now();
    // Watchdog: a frame that takes over a minute means Chrome or ffmpeg has stalled; exit so the caller can retry.
    let lastFrame = Date.now();
    const watchdog = setInterval(() => {
      if (Date.now() - lastFrame > 60000) { console.error("stalled: no frame for 60 s"); process.exit(2); }
    }, 5000);
    for (let f = 0; f < n; f++) {
      const jpg = await frame(from + f / fps);
      if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once("drain", r));
      lastFrame = Date.now();
      if (f % 150 === 0) console.log(`  frame ${f}/${n} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
    }
    ffmpeg.stdin.end();
    await done;
    clearInterval(watchdog);
    renameSync(`${out}.part`, out); // a failed render never replaces a good video
    console.log(`wrote ${out} (${n} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
} finally {
  close();
}

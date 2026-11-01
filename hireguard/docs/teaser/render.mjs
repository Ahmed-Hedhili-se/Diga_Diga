// Renders teaser.html to a seamless looping MP4 (H.264, 1920x1080, 30 fps, no audio) and a poster PNG.
//
//   node render.mjs --ffmpeg <path to ffmpeg> [--out <dir>] [--poster 9.6]
//   node render.mjs --stills 1.5,3,6,9.6,12.5          # PNG frames only, for checking
//
// ffmpeg: `pip install imageio-ffmpeg`, then python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())".
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { launch, newTab, sleep } from "../demo_video/video/cdp.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const OUT = path.resolve(arg("out", path.join(HERE, "out")));
const FPS = 30;
mkdirSync(OUT, { recursive: true });

const { cdp, close } = await launch();
try {
  const tab = await newTab(cdp);
  await tab.send("Page.enable");
  await tab.send("Runtime.enable");
  await tab.send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await tab.send("Page.navigate", { url: pathToFileURL(path.join(HERE, "teaser.html")).href + "?render=1" });
  const evaluate = async (expression) => {
    const r = await tab.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  for (let i = 0; i < 100 && !(await evaluate("typeof window.renderAt === 'function'").catch(() => false)); i++) await sleep(100);
  if (!(await evaluate("window.ready"))) console.warn("warning: Manrope / IBM Plex Mono did not load; frames use fallback fonts");
  const T = await evaluate("window.T");
  const frame = async (t, format) => {
    await evaluate(`renderAt(${t})`);
    const { data } = await tab.send("Page.captureScreenshot", { format, ...(format === "jpeg" ? { quality: 95 } : {}) });
    return Buffer.from(data, "base64");
  };

  const stills = arg("stills");
  if (stills) {
    for (const t of stills.split(",").map(Number)) writeFileSync(path.join(OUT, `still_${t}.png`), await frame(t, "png"));
    console.log(`stills in ${OUT}`);
  } else {
    const poster = Number(arg("poster", "9.6"));
    writeFileSync(path.join(OUT, "venidis_teaser_poster.png"), await frame(poster, "png"));
    const file = path.join(OUT, "venidis_teaser_loop.mp4");
    const ffmpeg = spawn(arg("ffmpeg", "ffmpeg"), [
      "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
      "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "animation", "-pix_fmt", "yuv420p",
      "-movflags", "+faststart", file,
    ], { stdio: ["pipe", "inherit", "inherit"] });
    const done = new Promise((res, rej) => ffmpeg.on("close", (code) => (code === 0 ? res() : rej(new Error(`ffmpeg exited ${code}`)))));
    const n = Math.round(T * FPS); // frames 0..n-1; frame n would equal frame 0, so the loop is seamless
    for (let i = 0; i < n; i++) {
      const png = await frame(i / FPS, "png");
      if (!ffmpeg.stdin.write(png)) await new Promise((r) => ffmpeg.stdin.once("drain", r));
      if (i % 60 === 0) process.stdout.write(`frame ${i}/${n}\r`);
    }
    ffmpeg.stdin.end();
    await done;
    console.log(`\n${file}`);
  }
} finally {
  close();
}

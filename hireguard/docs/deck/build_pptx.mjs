// Builds the PowerPoint version of the pitch deck from render_slides.mjs output: one full-bleed picture per slide
// (so Manrope and IBM Plex Mono look the same on any laptop), the speaker notes, the deck's sections, and on the
// teaser slide the real MP4, set to start with the slide and loop until stopped.
//
//   node render_slides.mjs --out build
//   NODE_PATH=<folder holding node_modules/pptxgenjs> node build_pptx.mjs --in build --out ../Venidis_pitch.pptx
//
// pptxgenjs 3.12 (npm install pptxgenjs@3.12.0 anywhere, then point NODE_PATH at its node_modules).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const PptxGenJS = require("pptxgenjs");
const JSZip = require("jszip");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const IN = path.resolve(arg("in", path.join(HERE, "build")));
const OUT = path.resolve(arg("out", path.join(HERE, "..", "Venidis_pitch.pptx")));
const { title, slides } = JSON.parse(readFileSync(path.join(IN, "slides.json"), "utf8"));
const blobs = JSON.parse(readFileSync(path.join(HERE, "blobs.json"), "utf8"));
const POSTER = path.resolve(HERE, blobs["6cc08b7e0d06c8a97a053a5dc2158e53"]);

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in, 16:9
pres.title = title;
pres.author = "Ahmed, Rayen, Hedhili, Yasmina";
pres.company = "Venidis";
const W = 13.333, H = 7.5;

let section = null;
const videoSlides = [];
slides.forEach((s, i) => {
  if (s.section || !section) {
    section = s.section || "Opening";
    pres.addSection({ title: section });
  }
  const slide = pres.addSlide({ sectionTitle: section });
  slide.background = { color: "0E1525" };
  if (s.video) {
    slide.addMedia({
      type: "video", path: s.video, x: 0, y: 0, w: W, h: H, objectName: "Venidis teaser",
      cover: "data:image/png;base64," + readFileSync(POSTER).toString("base64"),
    });
    videoSlides.push(i + 1);
  } else {
    slide.addImage({ path: path.join(IN, s.file), x: 0, y: 0, w: W, h: H, altText: s.title || s.id, objectName: s.id });
  }
  if (s.notes.trim()) slide.addNotes(s.notes.trim());
});

// pptxgenjs writes no timing, so a video waits for a click. Add PowerPoint's own "Start: Automatically" +
// "Loop until Stopped" timing tree for each video slide.
const timing = (spid, ms) => `<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst><p:par><p:cTn id="2" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst><p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:par><p:cTn id="4" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="afterEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr><p:cTn id="5" dur="${ms}" fill="hold"/><p:tgtEl><p:spTgt spid="${spid}"/></p:tgtEl></p:cBhvr></p:cmd></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par><p:video><p:cMediaNode vol="80000" mute="1"><p:cTn id="6" repeatCount="indefinite" fill="hold" display="0"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="${spid}"/></p:tgtEl></p:cMediaNode></p:video></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>`;

const zip = await JSZip.loadAsync(await pres.write({ outputType: "nodebuffer" }));
for (const n of videoSlides) {
  const name = `ppt/slides/slide${n}.xml`;
  let xml = await zip.file(name).async("string");
  const pic = xml.match(/<p:pic>[\s\S]*?<\/p:pic>/g)?.find((p) => p.includes("videoFile"));
  const spid = pic?.match(/<p:cNvPr id="(\d+)"/)?.[1];
  if (!spid) throw new Error(`no video shape on slide ${n}`);
  if (xml.includes("<p:timing>")) throw new Error(`slide ${n} already has timing`);
  xml = xml.includes("<p:extLst>") && xml.lastIndexOf("<p:extLst>") > xml.lastIndexOf("</p:cSld>")
    ? xml.replace(/<p:extLst>(?![\s\S]*<p:extLst>)/, timing(spid, 15000) + "<p:extLst>")
    : xml.replace("</p:sld>", timing(spid, 15000) + "</p:sld>");
  zip.file(name, xml);
}
const buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
(await import("node:fs")).writeFileSync(OUT, buf);
console.log(`${OUT}  ${slides.length} slides, video on slide ${videoSlides.join(", ")}, ${(buf.length / 1e6).toFixed(1)} MB`);

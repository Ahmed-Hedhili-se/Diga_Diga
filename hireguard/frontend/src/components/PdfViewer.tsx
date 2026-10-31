import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { apiBlob, errMsg } from "../api";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface Props {
  src: string;              // API path, e.g. /candidates/CAND-001/pdf
  page: number;             // 0-based
  highlight?: string | null;
  onPageCount?: (n: number) => void;
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

const norm = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();

/**
 * Renders the hostile PDF to a canvas with pdf.js (no plugin, no iframe, eval disabled),
 * and overlays boxes on text items that contain the evidence string.
 */
export default function PdfViewer({ src, page, highlight, onPageCount }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setDoc(null);
    setError(null);
    apiBlob(src)
      .then((b) => b.arrayBuffer())
      .then((buf) =>
        pdfjs.getDocument({
          data: new Uint8Array(buf),
          isEvalSupported: false,
          enableXfa: false,
          disableFontFace: false,
        }).promise,
      )
      .then((d) => {
        loaded = d;
        if (cancelled) return void d.destroy();
        setDoc(d);
        onPageCount?.(d.numPages);
      })
      .catch((e) => !cancelled && setError(errMsg(e)));
    return () => {
      cancelled = true;
      loaded?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    if (!doc || !canvasRef.current) return;
    let cancelled = false;
    const pageNo = Math.min(Math.max(page + 1, 1), doc.numPages);
    (async () => {
      const p = await doc.getPage(pageNo);
      const viewport = p.getViewport({ scale: 1.4 });
      const canvas = canvasRef.current!;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await p.render({ canvasContext: canvas.getContext("2d")!, viewport }).promise;
      if (cancelled) return;

      if (!highlight) return setBoxes([]);
      const needle = norm(highlight);
      if (!needle) return setBoxes([]);
      const content = await p.getTextContent();
      const items = content.items.filter((i): i is typeof i & { str: string; transform: number[]; width: number; height: number } => "str" in i);
      // concatenate normalized item strings, remember each item's char range
      let joined = "";
      const ranges: [number, number][] = [];
      for (const it of items) {
        const s = norm(it.str);
        const start = joined.length;
        joined += s + " ";
        ranges.push([start, start + s.length]);
      }
      const at = joined.indexOf(needle);
      if (at < 0) return setBoxes([]);
      const end = at + needle.length;
      const out: Box[] = [];
      items.forEach((it, idx) => {
        const [s, e] = ranges[idx];
        if (e <= at || s >= end) return;
        const [, , , d, x, y] = it.transform;
        const h = it.height || Math.abs(d);
        const [x1, y1, x2, y2] = viewport.convertToViewportRectangle([x, y, x + it.width, y + h]);
        out.push({
          left: Math.min(x1, x2),
          top: Math.min(y1, y2),
          width: Math.abs(x2 - x1),
          height: Math.abs(y2 - y1),
        });
      });
      if (!cancelled) setBoxes(out);
    })().catch((e) => !cancelled && setError(errMsg(e)));
    return () => {
      cancelled = true;
    };
  }, [doc, page, highlight]);

  return (
    <div className="pdf-wrap">
      {error && <div className="alert danger">PDF: {error}</div>}
      {!doc && !error && <div className="muted">Loading PDF…</div>}
      <div className="pdf-page">
        <canvas ref={canvasRef} />
        {boxes.map((b, i) => (
          <div key={i} className="pdf-hl" style={{ left: b.left, top: b.top, width: b.width, height: b.height }} />
        ))}
      </div>
    </div>
  );
}

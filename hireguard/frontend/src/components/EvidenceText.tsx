import { useEffect, useRef } from "react";
import type { Span } from "../types";

interface Props {
  text: string;
  pageOffsets: number[];
  page: number;
  span: Span | null;
}

export function pageOfOffset(offsets: number[], pos: number): number {
  let p = 0;
  for (let i = 0; i < offsets.length; i++) if (offsets[i] <= pos) p = i;
  return p;
}

/** Shows one page of visible_text with the evidence span marked. Text nodes only. */
export default function EvidenceText({ text, pageOffsets, page, span }: Props) {
  const markRef = useRef<HTMLElement>(null);
  const start = pageOffsets[page] ?? 0;
  const end = pageOffsets[page + 1] ?? text.length;

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [span, page]);

  if (!span || span.end <= start || span.start >= end) {
    return <pre className="evidence-text">{text.slice(start, end)}</pre>;
  }
  const s = Math.max(span.start, start);
  const e = Math.min(span.end, end);
  return (
    <pre className="evidence-text">
      {text.slice(start, s)}
      <mark ref={markRef}>{text.slice(s, e)}</mark>
      {text.slice(e, end)}
    </pre>
  );
}

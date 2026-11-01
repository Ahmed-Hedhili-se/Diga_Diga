// A row shows its most serious chips first, at most `max` of them, and folds the rest into "+N" (the hidden labels are in
// the title and the accessible name). Fewer chips per row is how the eye finds the one that matters.
import type { Tone } from "../lib/labels";
import { Badge } from "./ui";

export type Chip = { key: string; label: string; tone: Tone; title?: string };

const ORDER: Tone[] = ["danger", "warn", "info", "ok", "neutral"];

export function sortChips(chips: Chip[]): Chip[] {
  return [...chips].sort((a, b) => ORDER.indexOf(a.tone) - ORDER.indexOf(b.tone));
}

export default function ChipList({ chips, max = 2 }: { chips: Chip[]; max?: number }) {
  const sorted = sortChips(chips);
  const shown = sorted.slice(0, max);
  const hidden = sorted.slice(max);
  return (
    <>
      {shown.map((c) =>
        c.title ? (
          <span key={c.key} title={c.title}>
            <Badge tone={c.tone}>{c.label}</Badge>
          </span>
        ) : (
          <Badge key={c.key} tone={c.tone}>
            {c.label}
          </Badge>
        ),
      )}
      {hidden.length > 0 && (
        <span className="badge neutral" title={hidden.map((h) => h.label).join(", ")} aria-label={`${hidden.length} more: ${hidden.map((h) => h.label).join(", ")}`}>
          +{hidden.length}
        </span>
      )}
    </>
  );
}

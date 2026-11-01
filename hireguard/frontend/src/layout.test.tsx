// U1: cards in a row of a grid share one top edge. jsdom has no layout, so this guards the CSS rules themselves:
// the page-flow spacing may only match direct children of .content, and every grid container zeroes its children's margin.
import { describe, expect, it } from "vitest";
// @ts-ignore node builtin: the project has no @types/node, vitest runs in node
import { readFileSync } from "node:fs";

// vitest runs from frontend/
const css: string = (readFileSync as any)("src/styles.css", "utf8");

describe("card spacing rules", () => {
  it("only adds margin between cards that are direct children of .content", () => {
    const rules = css.split("}").filter((r: string) => /\.card\s*\+\s*\.card/.test(r));
    expect(rules).toHaveLength(1);
    expect(rules[0].trim().endsWith(".content > .card + .card { margin-top: 14px;")).toBe(true);
  });

  it("zeroes the top margin of children in every card grid", () => {
    const reset = css.split("}").find((r: string) => r.includes("margin-top: 0") && r.includes(".tiles > *"));
    expect(reset).toBeTruthy();
    for (const g of [".tiles", ".grid2", ".split", ".lanes", ".overview-grid"]) expect(reset).toContain(`${g} > *`);
  });
});

/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const stylesheet = (name: string) => readFileSync(new URL(name, import.meta.url), "utf8");
const globalStyles = stylesheet("./global.css");
const themeStyles = stylesheet("./themes.css");
const tokens = stylesheet("./tokens.css");

describe("TwelveHats work-card style contract", () => {
  it("defines the approved exact border tokens", () => {
    expect(tokens).toContain("--twelve-hats-panel-red: #c01529;");
    expect(tokens).toContain("--work-card-border-width: 2px;");
    expect(tokens).toContain("--work-card-border-style: solid;");
  });

  it("binds both themes to the same red border color", () => {
    expect(themeStyles.match(/--semantic-panel-outline: var\(--twelve-hats-panel-red\);/g)).toHaveLength(2);
  });

  it("enforces the contract on shared, primary, and dashboard work cards", () => {
    const approvedBorder = "border: var(--work-card-border-width) var(--work-card-border-style) var(--semantic-panel-outline);";
    expect(globalStyles.match(new RegExp(approvedBorder.replace(/[()]/g, "\\$&"), "g"))).toHaveLength(4);
    expect(globalStyles).not.toMatch(/twelve-hats-panel-outline\[data-panel-tone=.*border-(?:color|width)/s);
  });
});

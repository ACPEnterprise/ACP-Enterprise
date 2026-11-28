/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const globalStyles = readFileSync(resolve(process.cwd(), "src/styles/global.css"), "utf8");
const tokens = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

describe("mobile navigation style contract", () => {
  it("keeps the persistent navigation outside every sub-1024px layout", () => {
    expect(globalStyles).toMatch(/@media \(max-width: 63\.99rem\)[\s\S]*?\.theme-navigation-desktop\s*\{\s*display: none;/);
    expect(globalStyles).toMatch(/@media \(min-width: 64rem\)[\s\S]*?\.theme-shell\s*\{[\s\S]*?grid-template-columns:/);
    expect(globalStyles).toContain("--sidebar-width: 0px;");
  });

  it("defines a fixed overlay drawer and global horizontal overflow containment", () => {
    expect(globalStyles).toMatch(/\.theme-navigation-mobile\s*\{[\s\S]*?position: fixed;[\s\S]*?inset-inline-start: 0;/);
    expect(globalStyles).toMatch(/html,[\s\S]*?#root\s*\{[\s\S]*?overflow-x: hidden;[\s\S]*?overflow-x: clip;/);
    expect(globalStyles).toMatch(/\.theme-navigation-backdrop\s*\{\s*touch-action: none;/);
  });

  it("binds the header, workspace, and drawer to iPhone safe-area tokens", () => {
    for (const inset of ["top", "right", "bottom", "left"]) {
      expect(tokens).toContain(`--safe-area-${inset}: env(safe-area-inset-${inset}, 0px);`);
    }
    expect(globalStyles).toMatch(/\.safe-area-drawer\s*\{[\s\S]*?padding-top: var\(--safe-area-top\);[\s\S]*?padding-bottom: var\(--safe-area-bottom\);[\s\S]*?padding-left: var\(--safe-area-left\);/);
  });
});

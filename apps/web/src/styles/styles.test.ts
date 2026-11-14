import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return path.endsWith(".css") ? [path] : [];
  });
}

const TOKENS = join(SRC, "styles", "tokens.css");
const components = cssFiles(SRC).filter((f) => f !== TOKENS);
const strip = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

describe("locked design rules", () => {
  it("finds the component stylesheets", () => {
    expect(components.length).toBeGreaterThanOrEqual(4);
  });

  it("hard-codes no colour outside tokens.css", () => {
    for (const file of components) {
      const css = strip(readFileSync(file, "utf8"));
      expect(css.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/g), file).toBeNull();
    }
  });

  it("uses sharp corners only", () => {
    for (const file of [...components, TOKENS]) {
      const css = strip(readFileSync(file, "utf8"));
      const radii = [...css.matchAll(/border-radius:\s*([^;]+);/g)].map((m) => m[1]!.trim());
      expect(
        radii.filter((r) => r !== "0"),
        file,
      ).toEqual([]);
    }
  });

  it("draws no outline boxes around components", () => {
    for (const file of components) {
      const css = strip(readFileSync(file, "utf8"));
      const boxes = [...css.matchAll(/^\s*border:\s*([^;]+);/gm)]
        .map((m) => m[1]!.trim())
        .filter((v) => v !== "0" && v !== "none");
      expect(boxes, file).toEqual([]);
    }
  });

  it("sets the locked font and no display face", () => {
    const tokens = readFileSync(TOKENS, "utf8");
    expect(tokens).toContain("Atkinson Hyperlegible Next");
    expect(tokens).not.toMatch(/Bricolage/);
  });
});

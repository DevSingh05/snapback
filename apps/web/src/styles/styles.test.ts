import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
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

  // Vidyut, Sun Nov 15 03:0x: sharp corners read as harsh. One soft radius and a pill are allowed,
  // both as tokens; any other radius still fails.
  it("rounds corners only with the one radius token or the pill", () => {
    for (const file of [...components, TOKENS]) {
      const css = strip(readFileSync(file, "utf8"));
      const radii = [...css.matchAll(/border-radius:\s*([^;]+);/g)].map((m) => m[1]!.trim());
      expect(
        radii.filter((r) => !["0", "var(--radius)", "var(--radius-pill)"].includes(r)),
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

// Contrast floors for Day and the map at night, computed from tokens.css itself (WCAG relative luminance).
// Text (ink, muted, the accent) must reach 4.5:1 on the ground, the surface and the raised
// step; the night control edge must reach 3:1 on the ground and on the raised step.
type Rgba = [number, number, number, number];

function block(css: string, selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block in tokens.css`);
  const body = css.slice(start, css.indexOf("\n}", start));
  return new Map([...body.matchAll(/(--[a-z0-9-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!]));
}

function colour(vars: Map<string, string>, name: string): Rgba {
  const raw = vars.get(name);
  if (!raw) throw new Error(`${name} is not set`);
  const alias = /^var\((--[a-z0-9-]+)\)$/.exec(raw);
  if (alias) return colour(vars, alias[1]!);
  const hex = /^#([0-9a-f]{6})$/i.exec(raw);
  if (hex) {
    const n = parseInt(hex[1]!, 16);
    return [n >> 16, (n >> 8) & 255, n & 255, 1];
  }
  const rgb = /^rgb\((\d+) (\d+) (\d+)(?: \/ ([\d.]+))?\)$/.exec(raw);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3]), Number(rgb[4] ?? 1)];
  throw new Error(`${name}: cannot read ${raw}`);
}

const over = (top: Rgba, under: Rgba): Rgba => [
  top[0] * top[3] + under[0] * (1 - top[3]),
  top[1] * top[3] + under[1] * (1 - top[3]),
  top[2] * top[3] + under[2] * (1 - top[3]),
  1,
];

function luminance([r, g, b]: Rgba): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(fg: Rgba, bg: Rgba): number {
  const [hi, lo] = [luminance(over(fg, bg)), luminance(bg)].sort((a, b) => b - a) as [
    number,
    number,
  ];
  return (hi + 0.05) / (lo + 0.05);
}

describe("Day, and the map at night, contrast", () => {
  const css = strip(readFileSync(TOKENS, "utf8"));
  const day = block(css, ":root");
  const night = new Map([...day, ...block(css, '.city[data-theme="dark"]')]);
  const grounds = ["--paper", "--surface", "--layer-2"] as const;
  const report: string[] = [];

  for (const [theme, vars] of [
    ["Day", day],
    ["Map night", night],
  ] as const) {
    it(`${theme}: ink, muted and the accent read at 4.5:1 on ground, surface and raised`, () => {
      for (const fg of ["--ink", "--muted", "--act"])
        for (const bg of grounds) {
          const r = ratio(colour(vars, fg), colour(vars, bg));
          report.push(`${theme} ${fg} on ${bg}: ${r.toFixed(2)}`);
          expect(r, `${theme} ${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
    });

    it(`${theme}: text on the accent and on matte reads at 4.5:1`, () => {
      const pairs = [
        ["--on-act", "--act"],
        ["--on-act-matte", "--act-matte"],
        ["--on-matte", "--matte"],
        ["--act-matte", "--matte"],
        ["--on-matte-muted", "--matte"],
      ] as const;
      for (const [fg, bg] of pairs) {
        const r = ratio(colour(vars, fg), colour(vars, bg));
        report.push(`${theme} ${fg} on ${bg}: ${r.toFixed(2)}`);
        expect(r, `${theme} ${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    });

    it(`${theme}: every state square reads at 3:1 on ground, surface and raised`, () => {
      for (const st of ["ok", "mismatch", "warn", "unconfirmed", "unchecked"])
        for (const bg of grounds) {
          const r = ratio(colour(vars, `--st-${st}`), colour(vars, bg));
          report.push(`${theme} --st-${st} on ${bg}: ${r.toFixed(2)}`);
          expect(r, `${theme} --st-${st} on ${bg}`).toBeGreaterThanOrEqual(3);
        }
    });
  }

  it("control edges read at 3:1 in both themes, and night surfaces lift off the ground", () => {
    for (const [theme, vars] of [
      ["Day", day],
      ["Map night", night],
    ] as const)
      for (const bg of grounds) {
        const r = ratio(colour(vars, "--edge"), colour(vars, bg));
        report.push(`${theme} --edge on ${bg}: ${r.toFixed(2)}`);
        expect(r, `${theme} --edge on ${bg}`).toBeGreaterThanOrEqual(3);
      }
    // The night band is only a small step under the ground (theme-refs.md): a --line rule
    // closes it, so its floor is lower than the surface's.
    const steps = [
      ["--surface", "--paper", 1.2],
      ["--layer-2", "--surface", 1.2],
      ["--matte", "--paper", 1.15],
    ] as const;
    for (const [a, b, floor] of steps) {
      const r = ratio(colour(night, a), colour(night, b));
      report.push(`Map night ${a} against ${b}: ${r.toFixed(2)}`);
      expect(r, `${a} against ${b}`).toBeGreaterThanOrEqual(floor);
    }
  });

  // The focus ring is --focus: the accent on plaster, the matte accent on matte and photos.
  it("keeps the focus ring at 3:1 on plaster and on matte, in both themes", () => {
    const ui = strip(readFileSync(join(SRC, "ui", "ui.css"), "utf8"));
    for (const cls of [".ui-on-matte", ".ui-band"]) {
      const rule = new RegExp(`\\${cls} \\{[^}]*--focus:\\s*var\\(--act-matte\\)`).test(ui);
      expect(rule, `${cls} sets --focus to the matte accent`).toBe(true);
    }
    for (const [theme, vars] of [
      ["Day", day],
      ["Map night", night],
    ] as const) {
      for (const bg of grounds) {
        const r = ratio(colour(vars, "--focus"), colour(vars, bg));
        report.push(`${theme} focus ring (--focus) on ${bg}: ${r.toFixed(2)}`);
        expect(r, `${theme} --focus on ${bg}`).toBeGreaterThanOrEqual(3);
      }
      const onMatte = ratio(colour(vars, "--act-matte"), colour(vars, "--matte"));
      report.push(`${theme} focus ring on matte (--act-matte on --matte): ${onMatte.toFixed(2)}`);
      expect(onMatte, `${theme} focus on matte`).toBeGreaterThanOrEqual(3);
    }
  });

  it("keeps the dark look in one block, scoped to the map, and Day as the default", () => {
    expect(css.match(/color-scheme:\s*dark/g)).toHaveLength(1);
    expect(css).not.toMatch(/prefers-color-scheme/);
    expect(css).not.toMatch(/:root\[data-theme/);
    // CONTRAST_REPORT=<file> writes every ratio computed above, for the handoff.
    if (process.env.CONTRAST_REPORT) writeFileSync(process.env.CONTRAST_REPORT, report.join("\n"));
  });
});

// Reads eval/results.csv (columns defined by V6, issue #32). Nothing here makes up a number:
// every figure drawn comes from a row, and a bad row stops the parse with its line number.

export const COLUMNS = [
  "condition",
  "metric",
  "k",
  "n",
  "rate",
  "ci_low",
  "ci_high",
  "frozen_at",
] as const;

type Column = (typeof COLUMNS)[number];

export interface ResultRow {
  condition: string;
  metric: string;
  k: number;
  n: number;
  rate: number;
  ci_low: number;
  ci_high: number;
  frozen_at: string;
}

export class ResultsError extends Error {}

export function parseResults(text: string): ResultRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((raw, i) => ({ raw: raw.trim(), no: i + 1 }))
    .filter((l) => l.raw !== "" && !l.raw.startsWith("#"));
  if (lines.length === 0) return [];
  const header = lines[0]!.raw.split(",").map((h) => h.trim());
  const missing = COLUMNS.filter((c) => !header.includes(c));
  if (missing.length > 0) {
    throw new ResultsError(`results.csv is missing columns: ${missing.join(", ")}`);
  }
  const idx = Object.fromEntries(COLUMNS.map((c) => [c, header.indexOf(c)])) as Record<
    Column,
    number
  >;
  return lines.slice(1).map(({ raw, no }) => {
    const cells = raw.split(",").map((c) => c.trim());
    const text = (c: Column) => cells[idx[c]] ?? "";
    const num = (c: Column) => (text(c) === "" ? NaN : Number(text(c)));
    const row: ResultRow = {
      condition: text("condition"),
      metric: text("metric"),
      k: num("k"),
      n: num("n"),
      rate: num("rate"),
      ci_low: num("ci_low"),
      ci_high: num("ci_high"),
      frozen_at: text("frozen_at"),
    };
    const nums = [row.k, row.n, row.rate, row.ci_low, row.ci_high];
    const bad =
      row.condition === "" ||
      row.metric === "" ||
      nums.some((v) => !Number.isFinite(v)) ||
      row.k < 0 ||
      row.k > row.n ||
      row.rate < 0 ||
      row.rate > 1 ||
      row.ci_low > row.rate + 1e-9 ||
      row.ci_high < row.rate - 1e-9;
    if (bad) throw new ResultsError(`results.csv line ${no} is not a valid row`);
    return row;
  });
}

export const CURVE_METRIC = "forged_false_accept";
export const CURVE_ORDER = [
  "rules_only",
  "rules_plus_model_v0",
  "rules_plus_model_v1",
  "rules_plus_model_v2",
  "rules_plus_model_v2_memory",
] as const;

export const CONDITION_LABEL: Record<string, string> = {
  rules_only: "Rules only",
  rules_plus_model_v0: "Rules + model v0",
  rules_plus_model_v1: "Rules + model v1",
  rules_plus_model_v2: "Rules + model v2",
  rules_plus_model_v2_memory: "Rules + v2 + memory",
};

// Only conditions present in the file get a bar.
export function curveBars(rows: ResultRow[]): ResultRow[] {
  return CURVE_ORDER.flatMap((c) =>
    rows.filter((r) => r.condition === c && r.metric === CURVE_METRIC),
  );
}

export interface CalibrationPoint extends ResultRow {
  x: number;
}

const BIN = /^calibration_bin:(\d(?:\.\d+)?)-(\d(?:\.\d+)?)$/;

export function calibrationPoints(rows: ResultRow[]): CalibrationPoint[] {
  return rows
    .flatMap((r) => {
      const m = BIN.exec(r.metric);
      if (!m) return [];
      return [{ ...r, x: (Number(m[1]) + Number(m[2])) / 2 }];
    })
    .sort((a, b) => a.x - b.x);
}

export function linearScale(
  domain: [number, number],
  range: [number, number],
): (v: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (v) => {
    const t = Math.min(1, Math.max(0, (v - d0) / (d1 - d0)));
    return r0 + t * (r1 - r0);
  };
}

export const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import sample from "../../../../fixtures/contracts/results_sample.csv?raw";
import { LabPanel } from "./LabPanel";
import { ResultsError, calibrationPoints, curveBars, linearScale, parseResults } from "./results";

const HEADER = "condition,metric,k,n,rate,ci_low,ci_high,frozen_at";

describe("parseResults", () => {
  it("parses the fixture and skips # comment lines", () => {
    const rows = parseResults(sample);
    expect(rows).toHaveLength(11);
    expect(rows[0]).toMatchObject({ condition: "rules_only", k: 9, n: 40, rate: 0.225 });
  });

  it("returns no rows for an empty file or a header only", () => {
    expect(parseResults("")).toEqual([]);
    expect(parseResults(`${HEADER}\n`)).toEqual([]);
  });

  it("names the missing columns", () => {
    expect(() => parseResults("condition,metric,k\nrules_only,x,1\n")).toThrow(ResultsError);
    expect(() => parseResults("condition,metric,k\nrules_only,x,1\n")).toThrow(/n, rate, ci_low/);
  });

  it("rejects a row whose numbers are not numbers or whose interval does not hold the rate", () => {
    expect(() => parseResults(`${HEADER}\na,m,x,10,0.1,0,0.2,t`)).toThrow(/line 2/);
    expect(() => parseResults(`${HEADER}\na,m,1,10,0.5,0.1,0.2,t`)).toThrow(/line 2/);
    expect(() => parseResults(`${HEADER}\na,m,11,10,0.5,0.1,0.9,t`)).toThrow(/line 2/);
  });
});

describe("chart data and scales", () => {
  const rows = parseResults(sample);

  it("orders the curve bars rules only first, memory last, and keeps n", () => {
    const bars = curveBars(rows);
    expect(bars.map((b) => b.condition)).toEqual([
      "rules_only",
      "rules_plus_model_v0",
      "rules_plus_model_v1",
      "rules_plus_model_v2",
      "rules_plus_model_v2_memory",
    ]);
    expect(bars.every((b) => b.n === 40)).toBe(true);
  });

  it("reads calibration bins and sorts them by confidence", () => {
    const pts = calibrationPoints(rows);
    [0.55, 0.65, 0.75, 0.85, 0.95].forEach((x, i) => expect(pts[i]!.x).toBeCloseTo(x, 9));
    expect(pts).toHaveLength(5);
    expect(pts[0]).toMatchObject({ n: 8, k: 4 });
  });

  it("maps domain to range linearly and clamps", () => {
    const s = linearScale([0, 1], [100, 0]);
    expect(s(0)).toBe(100);
    expect(s(0.25)).toBe(75);
    expect(s(2)).toBe(0);
    expect(s(-1)).toBe(100);
  });
});

describe("LabPanel", () => {
  it("shows n and interval on every bar, and the FIXTURE chip", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    const bars = screen.getAllByTestId("curve-bar");
    expect(bars).toHaveLength(5);
    for (const bar of bars) {
      expect(within(bar).getByTestId("bar-n").textContent).toMatch(/^n = 40$/);
      expect(within(bar).getByTestId("bar-ci").textContent).toMatch(/95% CI \d/);
    }
  });

  it("states the safety rule", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    expect(
      screen.getByText(/Learned models can stop a pass. They can never call anyone a scammer./),
    ).toBeInTheDocument();
  });

  it("shows an empty state, not a chart, when the file has no rows", () => {
    render(<LabPanel csv={`${HEADER}\n`} source="live" />);
    expect(screen.getByTestId("lab-empty")).toHaveTextContent(/No results yet/);
    expect(screen.queryByTestId("curve-bar")).toBeNull();
  });

  it("shows the problem when columns are missing", () => {
    render(<LabPanel csv={"condition,metric\na,b"} source="live" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/missing columns/i);
  });

  it("invents no bar for a missing condition", () => {
    const only = `${HEADER}\nrules_only,forged_false_accept,9,40,0.225,0.1232,0.375,FIXTURE\n`;
    render(<LabPanel csv={only} source="fixture" />);
    expect(screen.getAllByTestId("curve-bar")).toHaveLength(1);
    expect(screen.getByTestId("calibration-empty")).toBeInTheDocument();
  });
});

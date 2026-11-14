import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import sample from "../../../../fixtures/contracts/results_sample.csv?raw";
import pr181 from "./calibration_pr181.csv?raw";
import { LabPanel, LabSection } from "./LabPanel";
import {
  ResultsError,
  calibrationPoints,
  curveBars,
  linearScale,
  niceTicks,
  parseResults,
} from "./results";

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

  it("accepts any rules_plus_model_vN_memory condition and puts it last", () => {
    const line = (c: string) => `${c},forged_false_accept,3,40,0.075,0.02,0.2,2026-11-13`;
    const parsed = parseResults(
      [
        HEADER,
        line("rules_plus_model_v1_memory"),
        line("rules_only"),
        line("rules_plus_model_v0_memory"),
      ].join("\n"),
    );
    expect(curveBars(parsed).map((b) => b.condition)).toEqual([
      "rules_only",
      "rules_plus_model_v0_memory",
      "rules_plus_model_v1_memory",
    ]);
  });

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

describe("review fixes", () => {
  const twoSeries = `${HEADER}
a_before,calibration_bin:0.80-0.90,5,10,0.5,0.2366,0.7634,FIXTURE
a_after,calibration_bin:0.80-0.90,9,10,0.9,0.5958,0.9821,FIXTURE
`;

  it("keeps conditions sharing a bin as separate series with a legend", () => {
    render(<LabPanel csv={twoSeries} source="fixture" />);
    expect(screen.getAllByTestId("cal-series")).toHaveLength(2);
    expect(screen.getAllByTestId("cal-point")).toHaveLength(2);
    const legend = screen.getByTestId("cal-legend");
    expect(within(legend).getByText("a_before")).toBeInTheDocument();
    expect(within(legend).getByText("a_after")).toBeInTheDocument();
  });

  it("shows memory catches k of n with its interval", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    expect(screen.getByTestId("memory-catch")).toHaveTextContent(
      "Memory catches 12 of 15 (80.0%, 95% CI 54.8% to 93.0%)",
    );
  });

  it("does not claim the attackers were unseen", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    expect(screen.queryByText(/never trained/)).toBeNull();
    expect(screen.getByText(/on the held-out set/)).toBeInTheDocument();
  });

  it("plots calibration on a 0 to 100% x axis", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    const svg = screen.getByTestId("calibration-chart");
    const labels = Array.from(svg.querySelectorAll("text.lab-tick")).map((t) => t.textContent);
    expect(labels.filter((l) => l === "0.0%")).toHaveLength(2);
    expect(calibrationPoints(parseResults(sample))[0]!.x).toBeCloseTo(0.55, 9);
  });

  it("rejects a rate that does not match k / n", () => {
    expect(() => parseResults(`${HEADER}\na,m,4,10,0.5,0.2,0.8,t`)).toThrow(/line 2/);
    expect(() => parseResults(`${HEADER}\na,m,0,0,0,0,0,t`)).toThrow(/line 2/);
    expect(() => parseResults(`${HEADER}\na,m,4,10,0.4,0.2,0.8,t`)).not.toThrow();
  });

  it("uses round axis ticks", () => {
    expect(niceTicks(0.375)).toEqual([0, 0.1, 0.2, 0.3, 0.4]);
    expect(niceTicks(1)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
  });
});

describe("LabSection against an API without results", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("falls back to the fixture sample with a FIXTURE chip on 404", async () => {
    vi.stubEnv("VITE_API_URL", "/api");
    vi.stubGlobal("fetch", async () => new Response("nope", { status: 404 }));
    render(<LabSection />);
    expect(await screen.findByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.queryByText(/not available/i)).not.toBeInTheDocument();
  });
});

describe("LabSection source label from the served file", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });
  const body = `${HEADER}\nrules_only,forged_false_accept,9,40,0.225,0.1232,0.375,t\n`;

  it("shows FIXTURE when the 200 body starts with # FIXTURE", async () => {
    vi.stubEnv("VITE_API_URL", "/api");
    vi.stubGlobal(
      "fetch",
      async () => new Response(`# FIXTURE synthetic\n${body}`, { status: 200 }),
    );
    render(<LabSection />);
    expect(await screen.findByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("shows LIVE for a 200 body without the marker", async () => {
    vi.stubEnv("VITE_API_URL", "/api");
    vi.stubGlobal("fetch", async () => new Response(body, { status: 200 }));
    render(<LabSection />);
    expect(await screen.findByTestId("source-chip")).toHaveTextContent("LIVE");
  });
});

// calibration_pr181.csv is the aggregate-count CSV from PR #181 (renders of our scans).
describe("calibration rows from renders (PR #181)", () => {
  it("does not print a frozen line from the calibration tag above FIXTURE data", () => {
    render(<LabPanel csv={pr181} source="fixture" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.queryByText(/frozen/i)).toBeNull();
    expect(screen.queryByText(/cal-20261114/)).toBeNull();
  });

  it("labels the series as renders and shows n per bin", () => {
    render(<LabPanel csv={pr181} source="fixture" />);
    const legend = screen.getByTestId("cal-legend");
    expect(within(legend).getByText("Renders of our scans (not photos)")).toBeInTheDocument();
    expect(within(legend).getByTestId("cal-legend-n")).toHaveTextContent(
      "n per bin: 37, 4, 3, 6, 30",
    );
    expect(screen.getAllByTestId("cal-point-n").map((t) => t.textContent)).toEqual([
      "n=37",
      "n=4",
      "n=3",
      "n=6",
      "n=30",
    ]);
  });

  it("retitles the heading and never frames a stated probability", () => {
    render(<LabPanel csv={pr181} source="fixture" />);
    expect(
      screen.getByRole("heading", { name: "Locate score calibration (renders of our scans)" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/when we say 90%/)).toBeNull();
  });

  it("still shows a real frozen date from a non-calibration row", () => {
    const csv = `${HEADER}
rules_only,forged_false_accept,9,40,0.225,0.1232,0.375,2026-11-13
place_real_renders,calibration_bin:0.90-1.00,30,30,1.0,0.8865,1.0,cal-20261114-0404
`;
    render(<LabPanel csv={csv} source="live" />);
    expect(screen.getByText(/Held-out set frozen 2026-11-13\./)).toBeInTheDocument();
  });

  it("main's current sample is unchanged: no frozen line, bins keyed by condition name", () => {
    render(<LabPanel csv={sample} source="fixture" />);
    expect(screen.queryByText(/frozen/i)).toBeNull();
    expect(screen.getAllByTestId("cal-series").length).toBeGreaterThan(0);
  });
});

// LOCAL STUB, to be swapped for fixtures/demo/evidence.fixture.json (contract E0) once lane A
// commits it. Case a copies that fixture's rows as posted in the E0 worktree on Nov 14; case b
// (one photo taken in another building) has no E0 fixture yet, so its rows are team-made
// synthetic values on the strict bar. Synthetic, describes no real home, always shown FIXTURE.
import type { EvidenceFile, PointPair } from "./types";

// Deterministic synthetic point pairs: no Math.random, so screenshots and tests are stable.
function pairs(n: number, seed: number, cluster: [number, number, number]): PointPair[] {
  let s = seed;
  const next = () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
  const [cx, cy, r] = cluster;
  const round = (v: number) => Math.round(Math.max(0.03, Math.min(0.97, v)) * 1000) / 1000;
  return Array.from({ length: n }, () => {
    const ax = cx + (next() - 0.5) * 2 * r;
    const ay = cy + (next() - 0.5) * 2 * r * 0.8;
    return [
      round(ax),
      round(ay),
      round(ax + (next() - 0.5) * 0.09),
      round(ay + (next() - 0.5) * 0.06),
    ];
  });
}

const BARS = {
  min_inliers: 30,
  min_inlier_ratio: 0.25,
  claimed_min_spread: 0.05,
  elsewhere_min_inliers: 50,
  elsewhere_min_spread: 0.15,
  ambiguity_ratio: 3.0,
};

export const EVIDENCE_STUB_A: EvidenceFile = {
  case_id: "fx-demo-a",
  source: "fixture",
  thresholds_version: "fixture-synthetic",
  bars: BARS,
  written_by: "code",
  photos: [
    {
      alias: "P1",
      status: "located_in_claimed",
      inliers: 142,
      inlier_ratio: 0.61,
      spread: 0.34,
      rival_ratio: 0.04,
      bar_failed: null,
      room_label: "Living Room",
      scan_alias: "S1",
      stop_alias: "stop-1",
      searches: [{ option: "base", chosen_by: "policy", seconds: 1.2, result: "placed" }],
      points: { n_total: 142, sampled: pairs(48, 11, [0.5, 0.5, 0.42]) },
    },
    {
      alias: "P2",
      status: "located_in_claimed",
      inliers: 96,
      inlier_ratio: 0.48,
      spread: 0.27,
      rival_ratio: 0.06,
      bar_failed: null,
      room_label: "Kitchen",
      scan_alias: "S1",
      stop_alias: "stop-2",
      searches: [{ option: "base", chosen_by: "policy", seconds: 1.1, result: "placed" }],
      points: { n_total: 96, sampled: pairs(48, 23, [0.48, 0.52, 0.38]) },
    },
    {
      alias: "P3",
      status: "located_in_claimed",
      inliers: 88,
      inlier_ratio: 0.41,
      spread: 0.31,
      rival_ratio: 0.05,
      bar_failed: null,
      room_label: "Bedroom",
      scan_alias: "S2",
      stop_alias: "stop-3",
      searches: [
        { option: "base", chosen_by: "policy", seconds: 1.3, result: "not_placed" },
        { option: "focus_scan:S2", chosen_by: "model", seconds: 2.1, result: "placed" },
      ],
      points: { n_total: 88, sampled: pairs(48, 37, [0.5, 0.48, 0.4]) },
    },
    {
      alias: "P4",
      status: "not_located",
      inliers: 24,
      inlier_ratio: 0.18,
      spread: 0.03,
      rival_ratio: 1.8,
      bar_failed: "inliers",
      room_label: null,
      scan_alias: null,
      stop_alias: null,
      searches: [
        { option: "base", chosen_by: "policy", seconds: 1.2, result: "not_placed" },
        { option: "stop", chosen_by: "policy", seconds: null, result: "skipped" },
      ],
      points: { n_total: 24, sampled: pairs(24, 53, [0.52, 0.3, 0.1]) },
    },
  ],
};

export const EVIDENCE_STUB_B: EvidenceFile = {
  case_id: "fx-demo-b",
  source: "fixture",
  thresholds_version: "fixture-synthetic",
  bars: BARS,
  written_by: "code",
  photos: [
    {
      alias: "P1",
      status: "located_elsewhere",
      inliers: 64,
      inlier_ratio: 0.44,
      spread: 0.22,
      rival_ratio: 0.08,
      bar_failed: null,
      room_label: "Kitchen",
      scan_alias: "S3",
      stop_alias: null,
      searches: [
        { option: "base", chosen_by: "policy", seconds: 1.2, result: "not_placed" },
        { option: "wider_index", chosen_by: "model", seconds: 2.4, result: "elsewhere" },
      ],
      points: { n_total: 64, sampled: pairs(48, 71, [0.5, 0.5, 0.36]) },
    },
  ],
};

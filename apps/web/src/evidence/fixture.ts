// The evidence fixture (contract E0), read from fixtures/demo/evidence.fixture.json: synthetic,
// team-made, always shown FIXTURE. Case a only. The copied-ad case (b) has no E0 fixture yet, so
// EVIDENCE_FIXTURE_B below is a team-made row on the strict bar until lane A posts one.
import raw from "../../../../fixtures/demo/evidence.fixture.json";
import type { EvidenceFile } from "./types";

export const EVIDENCE_FIXTURE_A = raw as unknown as EvidenceFile;

export const EVIDENCE_FIXTURE_B: EvidenceFile = {
  ...EVIDENCE_FIXTURE_A,
  case_id: "fx-demo-b",
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
      points: { n_total: 64, sampled: EVIDENCE_FIXTURE_A.photos[1]?.points?.sampled ?? [] },
    },
  ],
};

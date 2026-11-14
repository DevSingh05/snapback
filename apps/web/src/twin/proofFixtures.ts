import aerialFixture from "../../../../fixtures/contracts/aerial_tile.json";
import recordFixture from "../../../../fixtures/contracts/property_record.json";
import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { AerialTile, LocateResult, PropertyRecord } from "../contracts";
import type { AerialSide } from "./AerialProof";

// Two synthetic buildings for the two-building proof. The coordinates are made up (about 0.4 miles
// apart on a plain grid); no sponsor data and no addresses.
export const FIXTURE_CLAIMED: AerialSide = {
  tile: { ...(aerialFixture as AerialTile), property_id: "fx-prop-claimed", direction: "north" },
  record: { ...(recordFixture as PropertyRecord), property_id: "fx-prop-claimed", lat: 0, lon: 0 },
};

export const FIXTURE_MATCHED: AerialSide = {
  tile: { ...(aerialFixture as AerialTile), property_id: "fx-prop-matched", direction: "east" },
  record: {
    ...(recordFixture as PropertyRecord),
    property_id: "fx-prop-matched",
    lat: 0.0058,
    lon: 0,
  },
};

/** Demo scenario "copied": the one listing photo is placed in a different building (fixture only). */
export const COPIED_LOCATE: LocateResult = {
  ...(hold.locate as unknown as LocateResult),
  photos: [{ photo_id: "l1", status: "located_elsewhere", model_id: "fx-model-b" }],
  poses: {},
};

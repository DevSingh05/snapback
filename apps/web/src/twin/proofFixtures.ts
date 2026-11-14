import aerialFixture from "../../../../fixtures/contracts/aerial_tile.json";
import recordFixture from "../../../../fixtures/contracts/property_record.json";
import type { AerialTile, PropertyRecord } from "../contracts";
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

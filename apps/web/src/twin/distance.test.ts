import { describe, expect, it } from "vitest";

import { distanceAway, formatDistance, haversineMeters } from "./distance";

describe("haversineMeters", () => {
  it("is zero for the same point", () => {
    expect(haversineMeters({ lat: 10, lon: 20 }, { lat: 10, lon: 20 })).toBe(0);
  });
  it("matches a known value: one degree of latitude is about 111.2 km", () => {
    const m = haversineMeters({ lat: 0, lon: 0 }, { lat: 1, lon: 0 });
    expect(m).toBeGreaterThan(111_000);
    expect(m).toBeLessThan(111_400);
  });
});

describe("formatDistance", () => {
  it("uses feet below 1000 ft, rounded to the nearest 50 (nearest 10 under 100 ft)", () => {
    expect(formatDistance(274.32)).toBe("900 ft");
    expect(formatDistance(46)).toBe("150 ft");
    expect(formatDistance(10)).toBe("30 ft");
  });
  it("switches to miles at 1000 ft, one decimal", () => {
    expect(formatDistance(300)).toBe("0.2 miles"); // 984 ft rounds to 1000 ft
    expect(formatDistance(644)).toBe("0.4 miles");
    expect(formatDistance(2414)).toBe("1.5 miles");
  });
  it("says 1 mile, not 1.0 miles, and drops decimals from 10 miles", () => {
    expect(formatDistance(1609)).toBe("1 mile");
    expect(formatDistance(16_093)).toBe("10 miles");
    expect(formatDistance(48_280)).toBe("30 miles");
  });
  it("says under 30 ft for almost-zero distances", () => {
    expect(formatDistance(2)).toBe("under 30 ft");
  });
});

describe("distanceAway", () => {
  it("is null when either record lacks lat or lon", () => {
    expect(distanceAway({ lat: null, lon: 1 }, { lat: 0, lon: 0 })).toBeNull();
    expect(distanceAway({ lat: 0, lon: 0 }, { lat: undefined, lon: undefined })).toBeNull();
  });
  it("reads from the two records", () => {
    expect(distanceAway({ lat: 0, lon: 0 }, { lat: 0.0058, lon: 0 })).toBe("0.4 miles");
  });
});

import { describe, expect, it } from "vitest";

import { matchRoute } from "./App";

describe("matchRoute", () => {
  it("routes /case/:id/twin to the twin page", () => {
    expect(matchRoute("/case/fx-7Q2M/twin")).toEqual({ name: "twin", id: "fx-7Q2M" });
    expect(matchRoute("/case/fx-7Q2M/twin/")).toEqual({ name: "twin", id: "fx-7Q2M" });
  });

  it("still routes the result page", () => {
    expect(matchRoute("/case/fx-7Q2M")).toEqual({ name: "result", id: "fx-7Q2M" });
  });
});

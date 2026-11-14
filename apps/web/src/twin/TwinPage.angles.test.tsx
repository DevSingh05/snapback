import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";

const { fakeSdk } = vi.hoisted(() => ({
  fakeSdk: {
    disconnect: vi.fn(),
    Sweep: {
      moveTo: vi.fn().mockResolvedValue(undefined),
      data: {
        subscribe: (o: { onCollectionUpdated(c: Record<string, unknown>): void }) => {
          o.onCollectionUpdated({ "fx-sweep-03": {} });
          return { cancel: vi.fn() };
        },
      },
    },
  },
}));

vi.mock("./showcase", async (orig) => ({
  ...(await orig<typeof import("./showcase")>()),
  connectShowcase: vi.fn().mockResolvedValue(fakeSdk),
}));

import { TwinView } from "./TwinPage";

describe("TwinView flies to the locator's viewer angles (#244)", () => {
  it("passes yaw_deg and pitch_deg from the live pose to Sweep.moveTo", async () => {
    const locate = structuredClone(hold.locate) as unknown as LocateResult;
    locate.case_id = "live";
    locate.poses.l1 = { ...locate.poses.l1!, yaw_deg: -175.3, pitch_deg: -13.2 };
    render(<TwinView caseId="x" sdkKey="k" modelId="m" locate={locate} liveLocate />);
    await waitFor(() => expect(fakeSdk.Sweep.moveTo).toHaveBeenCalled());
    const [sweepId, options] = fakeSdk.Sweep.moveTo.mock.calls[0]!;
    expect(sweepId).toBe("fx-sweep-03");
    expect(options.rotation).toEqual({ x: -13.2, y: -175.3 });
  });
});

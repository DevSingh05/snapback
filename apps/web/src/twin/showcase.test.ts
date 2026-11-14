import { describe, expect, it, vi } from "vitest";

import { poseToSdkCall } from "./pose";
import { flyToPose, watchSweeps, type ShowcaseSdk } from "./showcase";

function fakeSdk() {
  const cancel = vi.fn();
  const moveTo = vi.fn().mockResolvedValue(undefined);
  let onUpdate: ((c: Record<string, unknown>) => void) | undefined;
  const sdk: ShowcaseSdk = {
    disconnect: vi.fn(),
    Sweep: {
      moveTo,
      data: {
        subscribe(o) {
          onUpdate = o.onCollectionUpdated;
          return { cancel };
        },
      },
    },
  };
  return { sdk, cancel, moveTo, emit: (c: Record<string, unknown>) => onUpdate?.(c) };
}

const call = poseToSdkCall({
  sweep_id: "fx-sweep-03",
  position: [0, 0, 0],
  rotation_quat: [0, 0, 0, 1],
  fov_deg: 70,
});

describe("flyToPose with a fake SDK", () => {
  it("calls Sweep.moveTo with the pose sweep and options", async () => {
    const { sdk, moveTo } = fakeSdk();
    expect(await flyToPose(sdk, call, ["fx-sweep-03"])).toEqual({ stand: false });
    expect(moveTo).toHaveBeenCalledWith("fx-sweep-03", call.options);
  });

  it("uses a stand-in sweep when the model lacks the pose sweep", async () => {
    const { sdk, moveTo } = fakeSdk();
    expect(await flyToPose(sdk, call, ["real-1"])).toEqual({ stand: true });
    expect(moveTo).toHaveBeenCalledWith("real-1", call.options);
  });

  it("does not call the SDK when the model has no sweeps", async () => {
    const { sdk, moveTo } = fakeSdk();
    expect(await flyToPose(sdk, call, [])).toBeNull();
    expect(moveTo).not.toHaveBeenCalled();
  });
});

describe("watchSweeps", () => {
  it("reports ids and cancels the subscription", () => {
    const { sdk, cancel, emit } = fakeSdk();
    const onIds = vi.fn();
    const stop = watchSweeps(sdk, onIds);
    emit({ a: {}, b: {} });
    expect(onIds).toHaveBeenCalledWith(["a", "b"]);
    stop();
    expect(cancel).toHaveBeenCalledOnce();
  });
});

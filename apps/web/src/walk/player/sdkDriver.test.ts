import { beforeEach, describe, expect, it, vi } from "vitest";

import { FIXTURE_TOUR } from "../../tour/fixtureTour";
import { createSdkDriver, type CameraDriver, type PlayerSdk } from "./sdkDriver";
import { PAN_DEG } from "./timeline";
import { Transport, fakeClock, type Cue } from "./transport";

const STOPS = FIXTURE_TOUR.stops;
const SWEEPS = ["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-04", "fx-sweep-06"];

function fakeSdk() {
  let onSweep: (s: { sid?: string }) => void = () => {};
  const sdk = {
    disconnect: vi.fn(),
    Sweep: {
      moveTo: vi.fn().mockResolvedValue(undefined),
      data: { subscribe: vi.fn() },
      current: {
        subscribe: (on: (s: { sid?: string }) => void) => {
          onSweep = on;
          return { cancel: vi.fn() };
        },
      },
    },
    Camera: { rotate: vi.fn().mockResolvedValue(undefined) },
  };
  return { sdk, walkTo: (sid: string) => onSweep({ sid }) };
}

/** The player's wiring without React: the transport's cues drive the camera. */
function wire(driver: CameraDriver) {
  const clock = fakeClock();
  const transport = new Transport(STOPS, {
    clock,
    onCue: (cue: Cue) => {
      if (cue.type === "stop") driver.goto(STOPS[cue.index]!, cue);
      if (cue.type === "pan") driver.pan(cue.deg, cue.ms);
    },
  });
  return { clock, transport };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("the scan's camera", () => {
  let fake: ReturnType<typeof fakeSdk>;
  let status: string[];
  let driver: CameraDriver;
  beforeEach(() => {
    fake = fakeSdk();
    status = [];
    driver = createSdkDriver(fake.sdk as unknown as PlayerSdk, {
      sweeps: SWEEPS,
      onStatus: (s) => status.push(s),
    });
  });

  it("moves through the stops' own sweeps in order as the tour plays", () => {
    const { clock, transport } = wire(driver);
    transport.play();
    clock.advance(transport.total);
    expect(fake.sdk.Sweep.moveTo.mock.calls.map((c) => c[0])).toEqual([
      "fx-sweep-00",
      "fx-sweep-01",
      "fx-sweep-03",
      "fx-sweep-06",
      "fx-sweep-04",
    ]);
    expect(fake.sdk.Sweep.moveTo.mock.calls[0]![1]).toMatchObject({
      transition: "transition.fly",
      transitionTime: 2000,
    });
  });

  it("pans with Camera.rotate once the camera has landed, at the pan's own speed", async () => {
    driver.goto(STOPS[1]!, { panDeg: 0, instant: false, speed: 1 });
    driver.pan(10, 500);
    expect(fake.sdk.Camera.rotate).not.toHaveBeenCalled(); // still flying
    await flush();
    driver.pan(10, 500);
    expect(fake.sdk.Camera.rotate).toHaveBeenCalledWith(10, 0, { speed: 20 });
    expect(status).toContain("At: Front door");
  });

  it("a seek into a pan arrives already turned, and flies faster at 1.5x", () => {
    driver.goto(STOPS[1]!, { panDeg: PAN_DEG / 2, instant: false, speed: 1.5 });
    const [sweep, options] = fake.sdk.Sweep.moveTo.mock.calls[0]!;
    expect(sweep).toBe("fx-sweep-00");
    expect(options.transitionTime).toBe(1333);
    expect(options.rotation.y).toBeCloseTo(PAN_DEG / 2);
  });

  it("calls nothing at all in explore mode, and resumes at the stop nearest the person", () => {
    const { clock, transport } = wire(driver);
    transport.play();
    clock.advance(7000);
    transport.explore();
    fake.sdk.Sweep.moveTo.mockClear();
    fake.sdk.Camera.rotate.mockClear();

    clock.advance(120_000);
    transport.exploreGoto(4);
    expect(fake.sdk.Sweep.moveTo).not.toHaveBeenCalled();
    expect(fake.sdk.Camera.rotate).not.toHaveBeenCalled();

    // They walked themselves to the bedroom's sweep; the tour picks up there.
    fake.walkTo("fx-sweep-04");
    const nearest = driver.nearestStop(STOPS);
    expect(STOPS[nearest!]!.title).toBe("Bedroom");
    transport.resume(nearest);
    expect(fake.sdk.Sweep.moveTo).toHaveBeenCalledTimes(1);
    expect(fake.sdk.Sweep.moveTo.mock.calls[0]![0]).toBe("fx-sweep-04");
  });

  it("never swaps in another sweep for a stop the model does not hold", () => {
    const partial = createSdkDriver(fake.sdk as unknown as PlayerSdk, {
      sweeps: ["fx-sweep-00"],
      onStatus: (s) => status.push(s),
    });
    partial.goto(STOPS[2]!, { panDeg: 0, instant: false, speed: 1 });
    expect(fake.sdk.Sweep.moveTo).not.toHaveBeenCalled();
    expect(status).toEqual(["This stop is not in the loaded 3D model"]);
  });

  it("walks the stops on an SDK with no Camera, and reports no nearest stop it cannot know", () => {
    const bare = {
      disconnect: vi.fn(),
      Sweep: { moveTo: vi.fn().mockResolvedValue(undefined), data: { subscribe: vi.fn() } },
    };
    const d = createSdkDriver(bare as unknown as PlayerSdk, { sweeps: SWEEPS });
    d.goto(STOPS[1]!, { panDeg: 0, instant: true, speed: 1 });
    d.pan(10, 500);
    expect(bare.Sweep.moveTo).toHaveBeenCalledWith(
      "fx-sweep-00",
      expect.objectContaining({ transition: "transition.instant", transitionTime: 0 }),
    );
    expect(d.nearestStop(STOPS)).toBeNull();
  });
});

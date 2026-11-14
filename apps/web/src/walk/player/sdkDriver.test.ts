import { beforeEach, describe, expect, it, vi } from "vitest";

import { FIXTURE_TOUR } from "../../tour/fixtureTour";
import { createSdkDriver, type CameraDriver, type PlayerSdk } from "./sdkDriver";
import { PAN_DEG } from "./timeline";
import { Transport, fakeClock, type Cue } from "./transport";

const STOPS = FIXTURE_TOUR.stops;
const SWEEPS = ["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-04", "fx-sweep-06"];

function fakeSdk(positions: Record<string, [number, number, number]> = {}) {
  let onSweep: (s: { sid?: string }) => void = () => {};
  const sdk = {
    disconnect: vi.fn(),
    Sweep: {
      moveTo: vi.fn().mockResolvedValue(undefined),
      data: {
        subscribe: (o: { onCollectionUpdated(c: Record<string, unknown>): void }) => {
          o.onCollectionUpdated(
            Object.fromEntries(
              Object.entries(positions).map(([sid, [x, y, z]]) => [sid, { position: { x, y, z } }]),
            ),
          );
          return { cancel: vi.fn() };
        },
      },
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
    // Camera.rotate(+) turns clockwise, which lowers the Showcase yaw: a seek lands where the pan would.
    expect(options.rotation.y).toBeCloseTo(-PAN_DEG / 2);
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

  describe("looking toward the next stop", () => {
    const at = (positions: Record<string, [number, number, number]>) => {
      const f = fakeSdk(positions);
      const d = createSdkDriver(f.sdk as unknown as PlayerSdk, { sweeps: SWEEPS });
      return { f, d };
    };
    // fx-sweep-00 is the first sweep stop; the next sweep stop is fx-sweep-01.
    const NEXT = STOPS[2]!;

    it("a room with no ad photo opens facing the next stop, half the pan to its left", () => {
      const { f, d } = at({ "fx-sweep-00": [0, 0, 0], "fx-sweep-01": [3, 0, 0] });
      d.goto(STOPS[1]!, { panDeg: 0, instant: false, speed: 1, next: NEXT });
      // +x is to the right of the default view: a quarter turn clockwise is yaw -90.
      expect(f.sdk.Sweep.moveTo.mock.calls[0]![1].rotation.y).toBeCloseTo(-90 + PAN_DEG / 2);
    });

    it("pans the way the next stop lies, never the long way round, and never past the cap", async () => {
      const photoStop = {
        ...STOPS[1]!,
        photos: [
          {
            photo_id: "p",
            alias: "P1",
            sweep_id: "fx-sweep-00",
            position: [0, 0, 0],
            rotation_quat: [0, 0, 0, 1],
            fov_deg: 65,
          },
        ],
      } as typeof NEXT;
      const right = at({ "fx-sweep-00": [0, 0, 0], "fx-sweep-01": [3, 0, 0] });
      right.d.goto(photoStop, { panDeg: 0, instant: false, speed: 1, next: NEXT });
      await flush();
      right.d.pan(10, 500);
      expect(right.f.sdk.Camera.rotate).toHaveBeenCalledWith(10, 0, { speed: 20 });

      const left = at({ "fx-sweep-00": [0, 0, 0], "fx-sweep-01": [-3, 0, 0] });
      left.d.goto(photoStop, { panDeg: 0, instant: false, speed: 1, next: NEXT });
      await flush();
      left.d.pan(10, 500);
      expect(left.f.sdk.Camera.rotate).toHaveBeenCalledWith(-10, 0, { speed: 20 });

      // Next stop dead ahead: nothing to turn toward, so the camera holds its heading.
      const ahead = at({ "fx-sweep-00": [0, 0, 0], "fx-sweep-01": [0, 0, -3] });
      ahead.d.goto(photoStop, { panDeg: 0, instant: false, speed: 1, next: NEXT });
      await flush();
      ahead.d.pan(10, 500);
      expect(ahead.f.sdk.Camera.rotate).not.toHaveBeenCalled();
    });

    it("keeps the plain pan when the sweeps' places are not known", async () => {
      const { f, d } = at({});
      d.goto(STOPS[1]!, { panDeg: 0, instant: false, speed: 1, next: NEXT });
      await flush();
      d.pan(10, 500);
      expect(f.sdk.Camera.rotate).toHaveBeenCalledWith(10, 0, { speed: 20 });
    });
  });
});

describe("opening outside on the real scan", () => {
  it("shows the whole model from above outside, then flies in to the first stop", async () => {
    const { sdk } = fakeSdk();
    const mode = { moveTo: vi.fn().mockResolvedValue(undefined) };
    const driver = createSdkDriver({ ...sdk, Mode: mode } as unknown as PlayerSdk, {
      sweeps: SWEEPS,
    });
    driver.goto(STOPS[0]!, { panDeg: 0, instant: false, speed: 1, next: STOPS[1] });
    expect(mode.moveTo).toHaveBeenCalledWith("mode.dollhouse", { transition: "transition.fly" });
    expect(sdk.Sweep.moveTo).not.toHaveBeenCalled();
    await Promise.resolve();
    await Promise.resolve();
    driver.goto(STOPS[1]!, { panDeg: 0, instant: false, speed: 1, next: STOPS[2] });
    expect(sdk.Sweep.moveTo).toHaveBeenCalledWith(
      "fx-sweep-00",
      expect.objectContaining({ transition: "transition.fly" }),
    );
  });

  it("without a dollhouse in the SDK, the opening beat leaves the camera alone", () => {
    const { sdk } = fakeSdk();
    const driver = createSdkDriver(sdk as unknown as PlayerSdk, { sweeps: SWEEPS });
    driver.goto(STOPS[0]!, { panDeg: 0, instant: false, speed: 1 });
    expect(sdk.Sweep.moveTo).not.toHaveBeenCalled();
  });
});

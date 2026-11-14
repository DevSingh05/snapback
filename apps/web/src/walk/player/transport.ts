import type { TourStop } from "../../contracts";
import {
  PAN_CHUNK_MS,
  PAN_DEG,
  PAN_MS,
  buildChapters,
  locate,
  momentAt,
  totalMs,
  type Chapter,
} from "./timeline";

// The transport: the tour's play head, with no React and no SDK in it. It is driven by a clock
// (the browser's frames in the app, a fake one in tests) and speaks to the outside in cues: go to
// a stop, pan the camera, land the photo. In explore mode it sends nothing at all.

export interface Clock {
  /** Call `onFrame` with the milliseconds since the last frame until the returned stop runs. */
  start(onFrame: (dtMs: number) => void): () => void;
}

export type Speed = 1 | 1.5;
export type Mode = "playing" | "paused" | "exploring";

export interface TransportState {
  mode: Mode;
  index: number;
  /** Tour time inside the current chapter, ms. */
  t: number;
  speed: Speed;
  reduced: boolean;
  /** False while the real 3D view is still loading: the play head waits. */
  ready: boolean;
  /** The play head ran to the end of the last chapter. */
  ended: boolean;
  /** The current stop's ad photo is in its one-second landing hold. */
  landing: boolean;
}

export type Cue =
  /** The tour is at this stop now: show it and put the camera there. */
  | { type: "stop"; index: number; panDeg: number; instant: boolean; speed: Speed }
  /** The stop on screen changed with no camera move (scrubbing, or a room picked in explore). */
  | { type: "index"; index: number }
  /** Turn the real camera by `deg` over `ms` of real time. */
  | { type: "pan"; index: number; deg: number; ms: number }
  /** Pin the stop's ad photo (true), or let it go as the pan starts (false). */
  | { type: "photo"; index: number; shown: boolean };

interface Options {
  clock: Clock;
  onCue?: (cue: Cue) => void;
  reduced?: boolean;
  ready?: boolean;
}

/** Above this point in a chapter, "previous" restarts the chapter instead of leaving it. */
const RESTART_MS = 1500;

export class Transport {
  readonly chapters: Chapter[];
  readonly total: number;
  onCue: (cue: Cue) => void;
  private state: TransportState;
  private readonly clock: Clock;
  private stopClock: (() => void) | null = null;
  private readonly listeners = new Set<() => void>();
  /** Pan time already sent to the camera for the current chapter. */
  private panSent = 0;
  private photoCue: "none" | "shown" | "released" = "none";

  constructor(stops: TourStop[], options: Options) {
    this.chapters = buildChapters(stops);
    this.total = totalMs(this.chapters);
    this.clock = options.clock;
    this.onCue = options.onCue ?? (() => {});
    this.state = {
      mode: "paused",
      index: 0,
      t: 0,
      speed: 1,
      reduced: options.reduced ?? false,
      ready: options.ready ?? true,
      ended: false,
      landing: false,
    };
  }

  getState = (): TransportState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Where the play head is on the whole timeline, ms. */
  position(): number {
    return (this.chapters[this.state.index]?.start ?? 0) + this.state.t;
  }

  play(): void {
    if (this.state.mode === "exploring") return this.resume();
    if (this.state.ended) this.place(0, 0, "stop");
    this.set({ mode: "playing", ended: false });
    this.run();
  }

  pause(): void {
    if (this.state.mode !== "playing") return;
    this.halt();
    this.set({ mode: "paused" });
  }

  toggle(): void {
    if (this.state.mode === "playing") this.pause();
    else this.play();
  }

  /** Jump to a point on the timeline: the stop, and how far into its dwell. */
  seek(ms: number): void {
    const { index, t } = locate(this.chapters, ms);
    this.leaveExplore();
    this.place(index, t, "stop");
  }

  /** Follow a drag on the scrubber: the stop on screen follows, the camera waits for `seek`. */
  scrub(ms: number): void {
    const { index, t } = locate(this.chapters, ms);
    this.leaveExplore();
    this.place(index, t, "index");
  }

  /** Go to the start of a chapter. Playing stays playing; explore ends, paused. */
  jumpTo(index: number): void {
    const chapter = this.chapters[Math.max(0, Math.min(index, this.chapters.length - 1))];
    if (chapter) this.seek(chapter.start);
  }

  next(): void {
    if (this.state.index < this.chapters.length - 1) this.jumpTo(this.state.index + 1);
  }

  /** Like a video: back to the start of this chapter, or to the one before when already there. */
  previous(): void {
    const { index, t } = this.state;
    this.jumpTo(t > RESTART_MS || index === 0 ? index : index - 1);
  }

  setSpeed(speed: Speed): void {
    this.set({ speed });
  }

  /** Reduced motion: the player stops, and from then on stops change in jumps with no pans. */
  setReduced(reduced: boolean): void {
    if (reduced === this.state.reduced) return;
    if (reduced) this.pause();
    this.set({ reduced });
  }

  setReady(ready: boolean): void {
    if (ready !== this.state.ready) this.set({ ready });
  }

  /** Send the current stop again, for a camera that has only just connected. */
  refresh(): void {
    if (this.state.mode === "exploring") return;
    this.place(this.state.index, this.state.t, "stop");
  }

  /** Hand the view to the person. The tour stops and no cue is sent until they resume. */
  explore(): void {
    if (this.state.mode === "exploring") return;
    this.halt();
    this.set({ mode: "exploring", landing: false });
  }

  /** In explore, the person picked a room: show it, and send nothing to the camera. */
  exploreGoto(index: number): void {
    if (this.state.mode !== "exploring" || !this.chapters[index]) return;
    this.set({ index, t: 0, ended: false });
    this.onCue({ type: "index", index });
  }

  /** Back to the timeline at the start of the nearest stop (the one given, else the current). */
  resume(nearest?: number | null): void {
    if (this.state.mode !== "exploring") return;
    const index = nearest != null && this.chapters[nearest] ? nearest : this.state.index;
    this.set({ mode: this.state.reduced ? "paused" : "playing", ended: false });
    this.place(index, 0, "stop");
    if (this.getState().mode === "playing") this.run();
  }

  destroy(): void {
    this.halt();
    this.listeners.clear();
  }

  // ---- inside ----

  private set(patch: Partial<TransportState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  private run(): void {
    if (this.stopClock) return;
    this.stopClock = this.clock.start((dt) => this.tick(dt));
  }

  private halt(): void {
    this.stopClock?.();
    this.stopClock = null;
  }

  private leaveExplore(): void {
    if (this.state.mode === "exploring") this.set({ mode: "paused" });
  }

  /** Put the play head at a chapter and time, and say so with one cue. */
  private place(index: number, t: number, cue: "stop" | "index"): void {
    const chapter = this.chapters[index];
    if (!chapter) return;
    const changed = index !== this.state.index;
    const moment = momentAt(chapter, t);
    const reduced = this.state.reduced;
    this.panSent = moment.panMs;
    this.photoCue =
      moment.phase === "arrive" ? "none" : moment.phase === "land" ? "shown" : "released";
    this.set({
      index,
      t,
      ended: this.state.ended && index === this.chapters.length - 1 && t >= chapter.duration,
      landing: chapter.land && moment.phase === "land",
    });
    if (cue === "stop")
      this.onCue({
        type: "stop",
        index,
        panDeg: reduced ? 0 : (PAN_DEG * moment.panMs) / PAN_MS,
        instant: reduced,
        speed: this.state.speed,
      });
    else if (changed) this.onCue({ type: "index", index });
  }

  private tick(dtMs: number): void {
    const s = this.state;
    if (s.mode !== "playing" || !s.ready) return;
    let index = s.index;
    let t = s.t + dtMs * s.speed;
    let chapter = this.chapters[index]!;
    while (t >= chapter.duration) {
      if (index >= this.chapters.length - 1) {
        this.halt();
        this.set({ t: chapter.duration, mode: "paused", ended: true, landing: false });
        return;
      }
      t -= chapter.duration;
      index += 1;
      chapter = this.chapters[index]!;
      this.place(index, 0, "stop");
    }
    const moment = momentAt(chapter, t);
    this.set({ t, landing: chapter.land && moment.phase === "land" });
    if (chapter.land && moment.phase !== "arrive" && this.photoCue === "none") {
      this.photoCue = "shown";
      this.onCue({ type: "photo", index, shown: true });
    }
    if (moment.phase !== "pan" || s.reduced) return;
    if (chapter.land && this.photoCue === "shown") {
      this.photoCue = "released";
      this.onCue({ type: "photo", index, shown: false });
    }
    while (moment.panMs >= this.panSent && this.panSent < PAN_MS) {
      this.panSent += PAN_CHUNK_MS;
      this.onCue({
        type: "pan",
        index,
        deg: (PAN_DEG * PAN_CHUNK_MS) / PAN_MS,
        ms: PAN_CHUNK_MS / s.speed,
      });
    }
  }
}

/** The app's clock: one call per animation frame. A long gap (a hidden tab) counts as 100 ms. */
export const frameClock: Clock = {
  start(onFrame) {
    let last = performance.now();
    let id = requestAnimationFrame(function frame(now) {
      onFrame(Math.min(Math.max(now - last, 0), 100));
      last = now;
      id = requestAnimationFrame(frame);
    });
    return () => cancelAnimationFrame(id);
  },
};

/** A clock for tests: time moves only when `advance` is called. */
export function fakeClock(): Clock & { advance(ms: number, stepMs?: number): void } {
  const frames = new Set<(dt: number) => void>();
  return {
    start(onFrame) {
      frames.add(onFrame);
      return () => frames.delete(onFrame);
    },
    advance(ms, stepMs = 50) {
      for (let left = ms; left > 0; left -= stepMs)
        for (const frame of [...frames]) if (frames.has(frame)) frame(Math.min(stepMs, left));
    },
  };
}

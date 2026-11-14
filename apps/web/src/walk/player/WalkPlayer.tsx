import {
  Component,
  createRef,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { TourStop } from "../../contracts";
import type { ShowcaseSdk } from "../../twin/showcase";
import { createSdkDriver, type CameraDriver, type PlayerSdk } from "./sdkDriver";
import {
  ARRIVE_MS,
  REST_POSE,
  captionOf,
  clockText,
  drawnPose,
  momentAt,
  type DrawnPose,
} from "./timeline";
import { Transport, frameClock, type Clock, type Cue } from "./transport";
import "./player.css";

// The walk as a video: play and pause, a scrubber with one chapter per stop, and an Explore
// switch that hands the view to the person. It mounts once, inside the tour's stage, and lays
// itself over it. It owns the camera of both views: the real scan through the Showcase SDK, and
// the drawn room through a few CSS variables it writes on the stage.

export interface WalkPlayerProps {
  stops: TourStop[];
  /** The stop on screen. The player follows it, and moves it through `onIndex`. */
  index: number;
  onIndex: (index: number) => void;
  reduced: boolean;
  /** The connected Showcase SDK, or null (fixture mode, still loading, or the wrong model). */
  sdk?: ShowcaseSdk | null;
  /** The loaded model's sweep ids. */
  sweeps?: string[];
  /** True while a real 3D view is expected and has not connected or failed yet: the tour waits. */
  loading?: boolean;
  onStatus?: (text: string) => void;
  /** Called when the tour pins (true) or lets go of (false) the stop's ad photo. */
  onPhoto?: (shown: boolean) => void;
  /** The one thing to do when the tour ends, shown on its end card. */
  endAction?: { label: string; href: string };
  /** What the walk found, in one line: it is the end card's headline when there is one. */
  summary?: string | null;
  /** Start playing on arrival, like a video. Never with reduced motion. */
  autoStart?: boolean;
  clock?: Clock;
}

type Surface = "scan" | "drawing" | "still";

const ZOOM_MIN = 1;
const ZOOM_MAX = 2.6;

export const REDUCED_NOTE =
  "Reduced motion is on, so the tour starts paused and jumps between stops with no camera pans.";

function surfaceOf(stage: HTMLElement | null, hasScan: boolean): Surface {
  const main = stage?.querySelector<HTMLElement>(".sv")?.dataset.main;
  if (main !== "real") return "drawing";
  return hasScan ? "scan" : "still";
}

function writePose(stage: HTMLElement, pose: DrawnPose): void {
  stage.style.setProperty("--wp-x", `${(pose.x * 100).toFixed(3)}%`);
  stage.style.setProperty("--wp-y", `${(pose.y * 100).toFixed(3)}%`);
  stage.style.setProperty("--wp-zoom", pose.zoom.toFixed(4));
  stage.style.setProperty("--wp-yaw", `${pose.yaw.toFixed(3)}deg`);
}

const typing = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  Boolean(
    el.closest("input, textarea, select, button, a, summary, [role=slider], [role=dialog]") ||
    el.isContentEditable,
  );

export function WalkPlayer({
  stops,
  index,
  onIndex,
  reduced,
  sdk = null,
  sweeps,
  loading = false,
  onStatus,
  onPhoto,
  endAction,
  summary,
  autoStart = true,
  clock = frameClock,
}: WalkPlayerProps) {
  const root = useRef<HTMLDivElement>(null);
  const stageOf = () => root.current?.parentElement ?? null;
  const [transport] = useState(() => new Transport(stops, { clock, reduced, ready: !loading }));
  const state = useSyncExternalStore(transport.subscribe, transport.getState);
  const exploring = state.mode === "exploring";
  const playing = state.mode === "playing";

  // The real camera, when the scan is connected.
  const driver = useMemo<CameraDriver | null>(
    () =>
      sdk && sweeps && sweeps.length > 0
        ? createSdkDriver(sdk as PlayerSdk, { sweeps, onStatus })
        : null,
    [sdk, sweeps], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const [surface, setSurface] = useState<Surface>("drawing");
  const live = useRef({ driver, onIndex, onPhoto, surface, stops });
  useEffect(() => {
    live.current = { driver, onIndex, onPhoto, surface, stops };
  });

  // Which view fills the stage: the scan, a real still, or the drawing.
  useEffect(() => {
    const stage = stageOf();
    if (!stage) return;
    const read = () => setSurface(surfaceOf(stage, Boolean(driver)));
    read();
    if (typeof MutationObserver === "undefined") return;
    const watch = new MutationObserver(read);
    watch.observe(stage, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-main"],
    });
    return () => watch.disconnect();
  }, [driver]);

  // The transport's cues, carried out.
  useEffect(() => {
    transport.onCue = (cue: Cue) => {
      const now = live.current;
      if (cue.type === "stop" || cue.type === "index") now.onIndex(cue.index);
      if (cue.type === "stop")
        now.driver?.goto(now.stops[cue.index]!, { ...cue, next: now.stops[cue.index + 1] });
      if (cue.type === "pan") now.driver?.pan(cue.deg, cue.ms);
      // The pinned photo only lines up with the scan while the camera holds still.
      if (cue.type === "photo" && (cue.shown || now.surface === "scan")) now.onPhoto?.(cue.shown);
    };
  }, [transport]);

  useEffect(() => {
    if (autoStart && !transport.getState().reduced) transport.play();
    return () => transport.destroy();
  }, [transport, autoStart]);
  useEffect(() => transport.setReduced(reduced), [transport, reduced]);
  useEffect(() => transport.setReady(!loading), [transport, loading]);
  // A camera that has just connected is sent to the stop on screen.
  useEffect(() => {
    if (driver) transport.refresh();
    return () => driver?.dispose();
  }, [transport, driver]);
  // The stop changed from outside the player (Next, Back, the room strip): follow it.
  useEffect(() => {
    if (index !== transport.getState().index) transport.jumpTo(index);
  }, [transport, index]);

  // The drawn stage's camera. During the tour it follows the play head; in explore, the person.
  const hand = useRef<DrawnPose>({ ...REST_POSE });
  const chapter = transport.chapters[state.index]!;
  const moment = momentAt(chapter, state.t);
  useEffect(() => {
    const stage = stageOf();
    if (!stage) return;
    if (exploring) writePose(stage, hand.current);
    else writePose(stage, reduced ? REST_POSE : drawnPose(moment.sweep));
  }, [exploring, reduced, moment.sweep]);
  useEffect(() => {
    const stage = stageOf();
    if (!stage) return;
    stage.dataset.wp = exploring ? "explore" : "tour";
    return () => {
      delete stage.dataset.wp;
      for (const name of ["--wp-x", "--wp-y", "--wp-zoom", "--wp-yaw"])
        stage.style.removeProperty(name);
    };
  }, [exploring]);

  // Space plays and pauses; left and right step a chapter. Never while typing or on a control.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      if (e.key === " " || e.code === "Space") transport.toggle();
      else if (e.key === "ArrowRight") transport.next();
      else if (e.key === "ArrowLeft") transport.previous();
      else return;
      e.preventDefault();
    };
    // Reading the rest of the page (the panel, the evidence, the room strip) pauses the tour.
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node | null;
      const page = root.current?.closest(".tour-page");
      if (!target || root.current?.contains(target) || !page?.contains(target)) return;
      transport.pause();
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown, true);
    };
  }, [transport]);

  // On the real scan the first touch must not be spent on the player: the scan takes the tap (a
  // tap on the floor walks there) and the page learns of it because the view takes the focus.
  // The player then hands over, exactly as if the person had pressed Explore.
  useEffect(() => {
    if (surface !== "scan" || exploring) return;
    const onBlur = () =>
      setTimeout(() => {
        const frame = document.activeElement;
        if (frame instanceof HTMLIFrameElement && stageOf()?.contains(frame))
          startExploreRef.current();
      }, 0);
    window.addEventListener("blur", onBlur);
    return () => window.removeEventListener("blur", onBlur);
  }, [surface, exploring]); // eslint-disable-line react-hooks/exhaustive-deps

  const startExplore = () => {
    hand.current = { ...(reduced ? REST_POSE : drawnPose(moment.sweep)) };
    transport.explore();
  };
  const startExploreRef = useRef(startExplore);
  useEffect(() => {
    startExploreRef.current = startExplore;
  });
  const resume = () => transport.resume(surface === "scan" ? driver?.nearestStop(stops) : null);

  // ---- the scrubber ----
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const msAt = (clientX: number) => {
    const box = track.current!.getBoundingClientRect();
    const u = box.width > 0 ? (clientX - box.left) / box.width : 0;
    return Math.max(0, Math.min(u, 1)) * transport.total;
  };
  const onTrackDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    transport.scrub(msAt(e.clientX));
  };
  const onTrackMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (dragging.current) transport.scrub(msAt(e.clientX));
  };
  const onTrackUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    transport.seek(msAt(e.clientX));
  };
  const onTrackKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const at = transport.position();
    const to =
      e.key === "ArrowRight"
        ? at + 1000
        : e.key === "ArrowLeft"
          ? at - 1000
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? transport.total
              : null;
    if (to === null) return;
    e.preventDefault();
    transport.seek(to);
  };

  // ---- explore on the drawn stage: drag to look around, scroll or the buttons to zoom ----
  const grab = useRef<{ x: number; y: number } | null>(null);
  const moveHand = (next: DrawnPose) => {
    const reach = 0.28 * next.zoom;
    hand.current = {
      zoom: Math.max(ZOOM_MIN, Math.min(next.zoom, ZOOM_MAX)),
      x: Math.max(-reach, Math.min(next.x, reach)),
      y: Math.max(-reach, Math.min(next.y, reach)),
      yaw: Math.max(-22, Math.min(next.yaw, 22)),
    };
    const stage = stageOf();
    if (stage) writePose(stage, hand.current);
  };
  // Any touch on the stage stops the tour and hands the view over; the drag carries straight on.
  const onShieldDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!exploring) startExplore();
    grab.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onShieldMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!grab.current) return;
    const box = e.currentTarget.getBoundingClientRect();
    const dx = (e.clientX - grab.current.x) / Math.max(box.width, 1);
    const dy = (e.clientY - grab.current.y) / Math.max(box.height, 1);
    grab.current = { x: e.clientX, y: e.clientY };
    const h = hand.current;
    // Dragging slides the room and turns it a little, the way a held model would.
    moveHand({ ...h, x: h.x + dx, y: h.y + dy, yaw: h.yaw + dx * 46 });
  };
  const onShieldUp = () => {
    grab.current = null;
  };
  const zoomBy = (factor: number) =>
    moveHand({ ...hand.current, zoom: hand.current.zoom * factor });
  useEffect(() => {
    const el = root.current?.querySelector<HTMLElement>(".wp-shield");
    if (!el || !exploring || surface === "scan") return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? 1.08 : 1 / 1.08);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [exploring, surface]); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = stops[state.index]!;
  const position = transport.position();
  const playLabel = playing ? "Pause" : state.ended ? "Play again" : "Play";

  return (
    <div
      ref={root}
      className="wp"
      data-testid="walk-player"
      data-mode={state.mode}
      data-surface={surface}
      data-ended={state.ended && !exploring ? "true" : undefined}
      data-motion={reduced ? "reduced" : "full"}
    >
      <Crossfade index={index} off={reduced} />
      <div
        className="wp-shield"
        data-testid="wp-shield"
        aria-hidden="true"
        onPointerDown={onShieldDown}
        onPointerMove={onShieldMove}
        onPointerUp={onShieldUp}
        onPointerCancel={onShieldUp}
      />

      <div className="wp-over" aria-live="polite">
        <p className="wp-room">
          <span className="wp-count mono">
            {state.index + 1}/{stops.length}
          </span>
          <strong>{stop.title}</strong>
        </p>
        {(loading || captionOf(stop)) && (
          <p className="wp-caption" data-testid="wp-caption">
            {loading ? "Loading the 3D view…" : captionOf(stop)}
          </p>
        )}
        {state.landing && (
          <p className="wp-pin" data-testid="wp-pin">
            <span className="wp-pin-mark" aria-hidden="true" />
            The ad photo lands here
          </p>
        )}
      </div>

      {state.ended && !exploring && (
        <div className="wp-end" data-testid="wp-end">
          <p className="wp-end-title">{summary || "That is the whole walk."}</p>
          <p className="wp-end-line">Now see it in person, before you pay anything.</p>
          <div className="wp-end-acts">
            {endAction && (
              <a className="wp-end-act" href={endAction.href}>
                {endAction.label}
              </a>
            )}
            <button type="button" className="wp-end-again" onClick={() => transport.play()}>
              Watch again
            </button>
          </div>
        </div>
      )}

      {!playing && !exploring && !loading && !state.ended && (
        <button
          type="button"
          className="wp-big"
          tabIndex={-1}
          aria-hidden="true"
          onClick={() => transport.play()}
        >
          <Icon name="play" />
        </button>
      )}

      <div className="wp-bar" role="group" aria-label="Tour player">
        {exploring ? (
          <div className="wp-explore" data-testid="wp-explore">
            <button type="button" className="wp-resume" data-testid="wp-resume" onClick={resume}>
              <Icon name="play" />
              Resume tour
            </button>
            {surface === "scan" ? (
              <p className="wp-hint">Tap the floor to walk. Drag to look around.</p>
            ) : (
              <>
                <p className="wp-hint">Drag to look around. Tap a room to go there.</p>
                <div className="wp-rooms" role="list" aria-label="Rooms">
                  {transport.chapters.map((c) => (
                    <span role="listitem" key={c.key}>
                      <button
                        type="button"
                        className="wp-chip"
                        aria-current={c.index === state.index ? "true" : undefined}
                        onClick={() => transport.exploreGoto(c.index)}
                      >
                        {c.title}
                      </button>
                    </span>
                  ))}
                </div>
                <div className="wp-zoom">
                  <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.25)}>
                    <Icon name="minus" />
                  </button>
                  <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>
                    <Icon name="plus" />
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <>
            <div
              ref={track}
              className="wp-track"
              data-testid="wp-scrubber"
              role="slider"
              tabIndex={0}
              aria-label="Tour timeline"
              aria-valuemin={0}
              aria-valuemax={Math.round(transport.total / 1000)}
              aria-valuenow={Math.round(position / 1000)}
              aria-valuetext={`${stop.title}, ${clockText(position)} of ${clockText(transport.total)}`}
              onPointerDown={onTrackDown}
              onPointerMove={onTrackMove}
              onPointerUp={onTrackUp}
              onPointerCancel={onTrackUp}
              onKeyDown={onTrackKey}
            >
              {transport.chapters.map((c) => {
                const done = Math.max(0, Math.min((position - c.start) / c.duration, 1));
                return (
                  <span
                    key={c.key}
                    className="wp-seg"
                    data-current={c.index === state.index ? "true" : undefined}
                    data-photo={c.land ? "true" : undefined}
                    style={
                      {
                        flexGrow: c.duration,
                        "--wp-notch": ARRIVE_MS / c.duration,
                      } as CSSProperties
                    }
                  >
                    <span className="wp-fill" style={{ transform: `scaleX(${done})` }} />
                  </span>
                );
              })}
              <span
                className="wp-thumb"
                style={{ left: `${(position / Math.max(transport.total, 1)) * 100}%` }}
              />
            </div>
            <div className="wp-chapters" data-testid="wp-chapters">
              {transport.chapters.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  className="wp-chapter"
                  style={{ flexGrow: c.duration }}
                  aria-current={c.index === state.index ? "true" : undefined}
                  aria-label={`Chapter ${c.index + 1}: ${c.title}`}
                  onClick={() => transport.jumpTo(c.index)}
                >
                  <span>{c.title}</span>
                </button>
              ))}
            </div>
            <div className="wp-row">
              <button
                type="button"
                className="wp-btn"
                aria-label="Previous chapter"
                onClick={() => transport.previous()}
              >
                <Icon name="previous" />
              </button>
              <button
                type="button"
                className="wp-btn wp-play"
                data-testid="wp-play"
                aria-label={playLabel}
                onClick={() => transport.toggle()}
              >
                <Icon name={playing ? "pause" : "play"} />
              </button>
              <button
                type="button"
                className="wp-btn"
                aria-label="Next chapter"
                disabled={state.index >= stops.length - 1}
                onClick={() => transport.next()}
              >
                <Icon name="next" />
              </button>
              <span className="wp-time mono" data-testid="wp-time">
                {clockText(position)} <span className="wp-dim">/ {clockText(transport.total)}</span>
              </span>
              <span className="wp-now" aria-hidden="true" />
              <button
                type="button"
                className="wp-btn wp-speed mono"
                data-testid="wp-speed"
                aria-label={`Speed ${state.speed}x. Change speed`}
                onClick={() => transport.setSpeed(state.speed === 1 ? 1.5 : 1)}
              >
                {state.speed}x
              </button>
              <button
                type="button"
                className="wp-btn wp-go"
                data-testid="wp-explore-toggle"
                onClick={startExplore}
              >
                <Icon name="explore" />
                Explore
              </button>
            </div>
          </>
        )}
        {reduced && (
          <p className="wp-reduced" data-testid="wp-reduced">
            {REDUCED_NOTE}
          </p>
        )}
      </div>
    </div>
  );
}

const ICONS = {
  play: "M7 4.5v15l12-7.5z",
  pause: "M6 4.5h4.2v15H6zM13.8 4.5H18v15h-4.2z",
  previous: "M5 5h2.6v14H5zM19 5v14L8.6 12z",
  next: "M16.4 5H19v14h-2.6zM5 5v14l10.4-7z",
  plus: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z",
  minus: "M5 11h14v2H5z",
  explore: "M12 2l2.6 7.4L22 12l-7.4 2.6L12 22l-2.6-7.4L2 12l7.4-2.6z",
} as const;

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg className="wp-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={ICONS[name]} />
    </svg>
  );
}

const FADE_MS = 520;

/**
 * The cut between two drawn rooms, as a crossfade. Just before the stage swaps rooms, the room
 * on screen is copied; the copy is laid over the new room and fades away. A class, because only
 * getSnapshotBeforeUpdate runs before the old room leaves the page.
 */
class Crossfade extends Component<{ index: number; off: boolean }> {
  private layer = createRef<HTMLDivElement>();

  override getSnapshotBeforeUpdate(before: { index: number }): HTMLElement | null {
    if (before.index === this.props.index || this.props.off) return null;
    const stage = this.layer.current?.closest(".wp")?.parentElement;
    const room = stage?.querySelector<HTMLElement>(
      '.sv-pane[data-view="drawing"][data-role="main"] .rs',
    );
    if (!room) return null;
    const ghost = room.cloneNode(true) as HTMLElement;
    // The copy keeps the camera it had, while the stage's camera starts over for the new room.
    const held = room.querySelector<HTMLElement>(".rs-svg, .rs-outside");
    const copy = ghost.querySelector<HTMLElement>(".rs-svg, .rs-outside");
    if (held && copy) copy.style.transform = getComputedStyle(held).transform;
    // The copy is a picture only: no names, no words, nothing a reader or a test can find.
    for (const el of [ghost, ...ghost.querySelectorAll<HTMLElement>("*")]) {
      for (const name of ["data-testid", "role", "aria-label", "id"]) el.removeAttribute(name);
      for (const node of [...el.childNodes]) if (node.nodeType === 3) node.textContent = "";
    }
    return ghost;
  }

  override componentDidUpdate(_p: unknown, _s: unknown, ghost: HTMLElement | null): void {
    const layer = this.layer.current;
    if (!ghost || !layer) return;
    layer.replaceChildren(ghost);
    setTimeout(() => ghost.remove(), FADE_MS);
  }

  override render() {
    return <div ref={this.layer} className="wp-ghost" aria-hidden="true" inert />;
  }
}

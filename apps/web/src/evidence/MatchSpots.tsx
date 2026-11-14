import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { STEP_MS, drawMs, fitPairs, pairTiers, pickSpots } from "./match";
import type { EvidencePhoto } from "./types";

interface Props {
  photo: EvidencePhoto;
  /** Real images come from our own server (E3). With none, team-made stand-ins are drawn. */
  adSrc?: string | null;
  scanSrc?: string | null;
  reduced: boolean;
  /** Stack the ad photo over the scan view (phones). */
  stacked?: boolean;
  /** A small still for the agent rail: four numbered pins, no captions, no controls. */
  mini?: boolean;
  /** Circles the spots again. Offered only when motion is allowed. */
  onReplay?: () => void;
}

const PANE_W = 440;
const PANE_H = 330;
const GAP = 56;
const GAP_STACKED = 20;
const GAP_MINI = 36;
/** A strip above each picture for its name, so no label ever covers a spot. */
const BAND = 42;
const MINI_SPOTS = 4;
const MINI_GAP = 0.26;

interface Pane {
  x: number;
  y: number;
}

/** Ring and number sizes in picture units: larger where the picture is drawn smaller. */
interface Size {
  r: number;
  tag: number;
}
const SIZE_SIDE: Size = { r: 17, tag: 21 };
const SIZE_STACKED: Size = { r: 20, tag: 26 };
const PIN_R = 33;
const GRIP_W = 26;
const GRIP_H = 56;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The opening peek: the ad photo slides over the scan view, holds, and slides back. */
const PEEK_OVER = 900;
const PEEK_HOLD = 600;
const PEEK_BACK = 700;
const PEEK_MS = PEEK_OVER + PEEK_HOLD + PEEK_BACK;
const ease = (t: number) => t * t * (3 - 2 * t);
function peekAt(ms: number): number {
  if (ms <= 0 || ms >= PEEK_MS) return 0;
  if (ms < PEEK_OVER) return ease(ms / PEEK_OVER);
  if (ms < PEEK_OVER + PEEK_HOLD) return 1;
  return 1 - ease((ms - PEEK_OVER - PEEK_HOLD) / PEEK_BACK);
}

/** How far the ad photo is laid over the scan view, 0 to 1. With `play`, it peeks across once
 *  after `wait` ms, then rests at 0; the first touch of the slider or the grip takes over. */
function useLay(wait: number, play: boolean): [number, (v: number) => void] {
  const [lay, setLay] = useState(0);
  const held = useRef(false);
  useEffect(() => {
    if (!play) return;
    let raf = 0;
    let start: number | null = null;
    const tick = (now: number) => {
      if (held.current) return;
      start ??= now;
      const ms = now - start - wait;
      setLay(peekAt(ms));
      if (ms < PEEK_MS) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [wait, play]);
  const set = useCallback((v: number) => {
    held.current = true;
    setLay(clamp(v, 0, 1));
  }, []);
  return [lay, set];
}

/** Where a point lands in its pane, kept far enough inside that its ring is whole. */
function place(pane: Pane, px: number, py: number, r: number): { cx: number; cy: number } {
  return {
    cx: clamp(pane.x + px * PANE_W, pane.x + r + 2, pane.x + PANE_W - r - 2),
    cy: clamp(pane.y + py * PANE_H, pane.y + r + 2, pane.y + PANE_H - r - 2),
  };
}

// One end of a numbered spot: a ring around the feature and its number on a small flag. The
// flag sits up and to the right, and moves to the other side at the pane's edge.
function Ring({
  pane,
  cx,
  cy,
  n,
  size,
  delay,
}: {
  pane: Pane;
  cx: number;
  cy: number;
  n: number;
  size: Size;
  delay?: CSSProperties;
}) {
  const { r, tag } = size;
  const reach = r * 0.62;
  const right = cx + reach + tag <= pane.x + PANE_W;
  const above = cy - reach - tag >= pane.y;
  const tx = right ? cx + reach : cx - reach - tag;
  const ty = above ? cy - reach - tag : cy + reach;
  return (
    <g className="ml-end">
      <circle className="ml-hit" cx={cx} cy={cy} r={r + 9} />
      <circle className="ml-ring-case" cx={cx} cy={cy} r={r} />
      <circle className="ml-ring" cx={cx} cy={cy} r={r} pathLength={1} style={delay} />
      <rect className="ml-flag" x={tx} y={ty} width={tag} height={tag} />
      <text className="ml-num" x={tx + tag / 2} y={ty + tag / 2} fontSize={tag * 0.68}>
        {n}
      </text>
    </g>
  );
}

function Pin({ cx, cy, n }: { cx: number; cy: number; n: number }) {
  return (
    <g className="ml-end">
      <circle className="ml-pin" cx={cx} cy={cy} r={PIN_R} />
      <text className="ml-num" x={cx} y={cy} fontSize={PIN_R * 1.15}>
        {n}
      </text>
    </g>
  );
}

// A team-made stand-in for a room picture: wall, floor boards, a paned window, wall cabinets, a
// counter with doors and a lamp. `shift` moves the pieces a little so the scan view reads as the
// same room from a nearby spot.
function StandIn({ at, shift }: { at: Pane; shift: number }) {
  const { x, y } = at;
  const boards = [252, 272, 296];
  return (
    <g className="ml-standin" aria-hidden="true">
      <rect className="ml-wall" x={x} y={y} width={PANE_W} height={PANE_H} />
      <rect className="ml-floor" x={x} y={y + 236} width={PANE_W} height={PANE_H - 236} />
      {boards.map((b) => (
        <rect key={b} className="ml-board" x={x} y={y + b} width={PANE_W} height={2} />
      ))}
      <rect className="ml-skirt" x={x} y={y + 230} width={PANE_W} height={6} />
      <rect className="ml-window" x={x + 52 + shift} y={y + 48} width={118} height={104} />
      <rect className="ml-sill" x={x + 109 + shift} y={y + 48} width={4} height={104} />
      <rect className="ml-sill" x={x + 52 + shift} y={y + 98} width={118} height={4} />
      <rect className="ml-sill" x={x + 44 + shift} y={y + 152} width={134} height={8} />
      <rect className="ml-cabinet" x={x + 232 + shift} y={y + 40} width={150} height={58} />
      <rect className="ml-seam" x={x + 281 + shift} y={y + 40} width={2} height={58} />
      <rect className="ml-seam" x={x + 331 + shift} y={y + 40} width={2} height={58} />
      <rect className="ml-counter" x={x + 214 + shift} y={y + 168} width={190} height={100} />
      <rect className="ml-seam" x={x + 276 + shift} y={y + 176} width={2} height={86} />
      <rect className="ml-seam" x={x + 340 + shift} y={y + 176} width={2} height={86} />
      <rect className="ml-top" x={x + 206 + shift} y={y + 158} width={206} height={12} />
      <rect className="ml-cabinet" x={x + 372 + shift} y={y + 120} width={22} height={38} />
      <rect className="ml-shadow" x={x + 214 + shift} y={y + 268} width={190} height={8} />
    </g>
  );
}

// The ad photo and the scan view on one dark table, read like a spot-the-difference answer key:
// a few matched spots, spread out, carry the same number in both pictures. Pointing at a number
// lights that one pair and draws its only connector. One slider lays the ad photo over the scan
// view, lined up by the matched points, so the numbered rings land on the same things in both.
// Every drawn point sits behind a small switch. The points are a sample: the caption always says how many are shown out of how many
// matched.
export function MatchSpots({
  photo,
  adSrc,
  scanSrc,
  reduced,
  stacked = false,
  mini = false,
  onReplay,
}: Props) {
  const all = photo.points?.sampled ?? [];
  const total = photo.points?.n_total ?? 0;
  const [every, setEvery] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const lit = hover ?? pinned;
  const clip = useId();
  const svg = useRef<SVGSVGElement>(null);

  const spots = mini ? pickSpots(all, MINI_SPOTS, MINI_GAP) : pickSpots(all);
  const shown = every ? all.map((_, i) => i) : spots;
  const tiers = every ? pairTiers(all) : [];
  const gap = mini ? GAP_MINI : stacked ? GAP_STACKED : GAP;
  const band = mini ? 0 : BAND;
  const a: Pane = { x: 0, y: band };
  const b: Pane = stacked ? { x: 0, y: band * 2 + PANE_H + gap } : { x: PANE_W + gap, y: band };
  const width = stacked ? PANE_W : PANE_W * 2 + gap;
  const height = b.y + PANE_H;
  const size = stacked ? SIZE_STACKED : SIZE_SIDE;
  const r = mini ? PIN_R : every ? 5 : size.r;
  const weak = Boolean(photo.bar_failed) || photo.status === "not_located";
  const caption = every
    ? `${all.length} of ${total} matched points drawn`
    : `${spots.length} of ${total} matched points shown`;
  const still = reduced || mini || every;
  const [lay, setLay] = useLay(drawMs(spots.length), !reduced && !mini && all.length > 0);
  // The ad photo in the scan view's frame: the fit, moved from 0-to-1 into picture units.
  const fit = fitPairs(all);
  const over = `matrix(${fit.xx} ${(fit.yx * PANE_H) / PANE_W} ${(fit.xy * PANE_W) / PANE_H} ${fit.yy} ${b.x + fit.x0 * PANE_W} ${b.y + fit.y0 * PANE_H})`;
  const seam = b.x + lay * PANE_W;
  const grip = clamp(seam, b.x + (stacked ? GRIP_W / 2 : 0), b.x + PANE_W - GRIP_W / 2);
  const drag = (e: ReactPointerEvent<SVGGElement>) => {
    const ctm = svg.current?.getScreenCTM();
    if (!ctm) return;
    const at = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    setLay((at.x - b.x) / PANE_W);
  };
  const ends = shown.map((i) => {
    const [ax, ay, bx, by] = all[i]!;
    return { i, from: place(a, ax, ay, r), to: place(b, bx, by, r) };
  });
  const link = lit == null ? undefined : ends[lit];
  const pick = (k: number) => setPinned((was) => (was === k ? null : k));
  const hint =
    lit != null && !every
      ? `Spot ${lit + 1}: the same place in the ad photo and in the scan view.`
      : lay > 0
        ? "The ad photo, laid over the scan view and lined up by the matched points."
        : every
          ? "Brighter points agree most closely with the rest."
          : weak
            ? "These spots lined up, but too few points did to say it's this room."
            : "Same number, same spot in both pictures. Pick a number to light its pair.";

  return (
    <figure
      className={`ml${mini ? " ml-mini" : ""}`}
      data-testid="match-view"
      data-motion={reduced ? "reduced" : "full"}
      data-layout={stacked ? "stacked" : "side"}
      data-mode={every ? "every" : "spots"}
      data-weak={weak ? "true" : undefined}
      style={
        {
          "--b-left": `${(b.x / width) * 100}%`,
          "--b-top": `${((b.y - band) / height) * 100}%`,
          "--band": `${(band / height) * 100}%`,
        } as CSSProperties
      }
    >
      <div className="ml-table">
        <svg
          ref={svg}
          className="ml-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${caption}, at the same places on the ad photo and the scan view`}
        >
          {adSrc ? (
            <image
              href={adSrc}
              x={a.x}
              y={a.y}
              width={PANE_W}
              height={PANE_H}
              preserveAspectRatio="xMidYMid slice"
            />
          ) : (
            <StandIn at={a} shift={0} />
          )}
          {scanSrc ? (
            <image
              href={scanSrc}
              x={b.x}
              y={b.y}
              width={PANE_W}
              height={PANE_H}
              preserveAspectRatio="xMidYMid slice"
            />
          ) : (
            <StandIn at={b} shift={Math.round(fit.x0 * PANE_W)} />
          )}
          <rect
            className={adSrc ? "ml-scrim-real" : "ml-scrim-ad"}
            x={a.x}
            y={a.y}
            width={PANE_W}
            height={PANE_H}
          />
          <rect
            className={scanSrc ? "ml-scrim-real" : "ml-scrim"}
            x={b.x}
            y={b.y}
            width={PANE_W}
            height={PANE_H}
          />
          {!mini && lay > 0 && (
            <g data-testid="match-over">
              <clipPath id={clip}>
                <rect x={b.x} y={b.y} width={lay * PANE_W} height={PANE_H} />
              </clipPath>
              <g clipPath={`url(#${clip})`}>
                <rect className="ml-under" x={b.x} y={b.y} width={PANE_W} height={PANE_H} />
                <g transform={over}>
                  {adSrc ? (
                    <image
                      href={adSrc}
                      x={0}
                      y={0}
                      width={PANE_W}
                      height={PANE_H}
                      preserveAspectRatio="xMidYMid slice"
                    />
                  ) : (
                    <StandIn at={{ x: 0, y: 0 }} shift={0} />
                  )}
                </g>
                <rect
                  className={adSrc ? "ml-scrim-real" : "ml-scrim-ad"}
                  x={b.x}
                  y={b.y}
                  width={PANE_W}
                  height={PANE_H}
                />
              </g>
              <rect className="ml-seam-line" x={seam - 1.5} y={b.y} width={3} height={PANE_H} />
            </g>
          )}
          {link && (
            <line
              className="ml-link"
              data-testid="match-link"
              x1={link.from.cx}
              y1={link.from.cy}
              x2={link.to.cx}
              y2={link.to.cy}
            />
          )}
          <g className="ml-marks" data-lit={lit != null ? "true" : undefined}>
            {ends.map(({ i, from, to }, k) => {
              const on = lit === k ? "true" : undefined;
              const point = {
                onMouseEnter: mini ? undefined : () => setHover(k),
                onMouseLeave: mini ? undefined : () => setHover(null),
                onClick: mini ? undefined : () => pick(k),
              };
              if (every)
                return (
                  <g
                    key={i}
                    className={`ml-pair ml-${tiers[i]}`}
                    data-testid="match-pair"
                    data-tier={tiers[i]}
                    data-on={on}
                    {...point}
                  >
                    {[from, to].map((p, e) => (
                      <g key={e} className="ml-end">
                        <circle className="ml-hit" cx={p.cx} cy={p.cy} r={10} />
                        <rect className="ml-dot" x={p.cx - 4} y={p.cy - 4} width={8} height={8} />
                      </g>
                    ))}
                  </g>
                );
              const delay = still ? undefined : { animationDelay: `${k * STEP_MS}ms` };
              return (
                <g
                  key={i}
                  className="ml-spot"
                  data-testid="match-spot"
                  data-on={on}
                  style={delay}
                  {...point}
                >
                  {mini ? (
                    <>
                      <Pin cx={from.cx} cy={from.cy} n={k + 1} />
                      <Pin cx={to.cx} cy={to.cy} n={k + 1} />
                    </>
                  ) : (
                    <>
                      <Ring pane={a} {...from} n={k + 1} size={size} delay={delay} />
                      <Ring pane={b} {...to} n={k + 1} size={size} delay={delay} />
                    </>
                  )}
                </g>
              );
            })}
          </g>
          {!mini && (
            <g
              className="ml-grip"
              aria-hidden="true"
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture?.(e.pointerId);
                drag(e);
              }}
              onPointerMove={(e) => {
                if (e.currentTarget.hasPointerCapture?.(e.pointerId)) drag(e);
              }}
            >
              <rect
                className="ml-hit"
                x={grip - GRIP_W}
                y={b.y + PANE_H / 2 - GRIP_H}
                width={GRIP_W * 2}
                height={GRIP_H * 2}
              />
              <rect
                className="ml-grip-tab"
                x={grip - GRIP_W / 2}
                y={b.y + PANE_H / 2 - GRIP_H / 2}
                width={GRIP_W}
                height={GRIP_H}
              />
              <path
                className="ml-grip-mark"
                d={`M${grip - 3} ${b.y + PANE_H / 2 - 7}l-6 7l6 7zM${grip + 3} ${b.y + PANE_H / 2 - 7}l6 7l-6 7z`}
              />
            </g>
          )}
        </svg>
        {!mini && (
          <>
            <span className="ml-tag ml-tag-a">
              Ad photo <span className="mono">{photo.alias}</span>
              {!adSrc && <span className="ml-note"> (stand-in drawing)</span>}
            </span>
            <span className="ml-tag ml-tag-b">
              Scan view{photo.scan_alias ? " " : ""}
              {photo.scan_alias && <span className="mono">{photo.scan_alias}</span>}
              {!scanSrc && <span className="ml-note"> (stand-in drawing)</span>}
            </span>
          </>
        )}
      </div>
      {!mini && (
        <figcaption className="ml-caption">
          <div className="ml-pick">
            {every ? (
              <span className="ml-legend" aria-hidden="true">
                <span className="ml-key ml-key-strong" />
                <span className="ml-key ml-key-mid" />
                <span className="ml-key ml-key-faint" />
              </span>
            ) : (
              <div className="ml-strip" role="group" aria-label="Matched spots">
                {spots.map((i, k) => (
                  <button
                    key={i}
                    type="button"
                    className="ml-chip mono"
                    aria-label={`Spot ${k + 1}`}
                    aria-pressed={pinned === k}
                    data-on={lit === k ? "true" : undefined}
                    onClick={() => pick(k)}
                    onMouseEnter={() => setHover(k)}
                    onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(k)}
                    onBlur={() => setHover(null)}
                  >
                    {k + 1}
                  </button>
                ))}
              </div>
            )}
            <p className="ml-hint" data-testid="match-hint" aria-live="polite">
              {hint}
            </p>
            <span className="ml-count mono" data-testid="match-count">
              {caption}
            </span>
          </div>
          <div className="ml-foot">
            <label className="ml-lay">
              <span className="ml-lay-text">Lay the ad photo over the scan view</span>
              <input
                type="range"
                className="ml-lay-range"
                data-testid="match-lay"
                min={0}
                max={100}
                step={1}
                value={Math.round(lay * 100)}
                aria-valuetext={`${Math.round(lay * 100)} percent laid over`}
                onChange={(e) => setLay(Number(e.target.value) / 100)}
              />
            </label>
            {all.length > spots.length && (
              <button
                type="button"
                className="ml-more"
                data-testid="match-every"
                onClick={() => {
                  setEvery((v) => !v);
                  setPinned(null);
                  setHover(null);
                }}
              >
                {every ? `Back to ${spots.length} spots` : `Show all ${all.length} points`}
              </button>
            )}
            {onReplay && !reduced && !every && (
              <button type="button" className="ml-more" onClick={onReplay}>
                Replay
              </button>
            )}
          </div>
        </figcaption>
      )}
    </figure>
  );
}

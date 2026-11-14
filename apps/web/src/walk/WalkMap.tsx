import { Parts } from "../draw/Parts";
import { makeScene, part, type Part } from "../draw/kit";
import type { TourStop } from "../contracts";
import "./walk.css";

// The walk as a small lit model: one block per stop inside the home, in walking order, with
// the room you are in raised and lit and a path joining them. It is a guide to the order of the
// walk, not a floor plan, and it says so.

const PER_ROW = 3;
const CELL = 46;
const W = 34;
const D = 30;
const s = makeScene({ ox: 120, oy: 22 });

interface Cell {
  stop: TourStop;
  index: number; // index in the plan's stops
  x: number;
  y: number;
}

/** Stops inside the home, laid out as a snake so each is next to the one before it. */
export function walkCells(stops: TourStop[]): Cell[] {
  return stops
    .map((stop, index) => ({ stop, index }))
    .filter(({ stop }) => stop.kind !== "arrive" && stop.kind !== "outro")
    .map(({ stop, index }, i) => {
      const row = Math.floor(i / PER_ROW);
      const col = row % 2 === 0 ? i % PER_ROW : PER_ROW - 1 - (i % PER_ROW);
      return { stop, index, x: col * CELL, y: row * CELL };
    });
}

interface Props {
  stops: TourStop[];
  /** Index of the current stop in `stops`. */
  current: number;
  onPick: (index: number) => void;
}

export function WalkMap({ stops, current, onPick }: Props) {
  const cells = walkCells(stops);
  if (cells.length < 2) return null;
  const rows = Math.ceil(cells.length / PER_ROW);
  const here = cells.find((c) => c.index === current);
  const base: Part[] = [
    part("slab", [
      s.contact(-8, -8, PER_ROW * CELL + 4, rows * CELL + 4, 7),
      ...s.box("white", -8, -8, -5, PER_ROW * CELL + 4, rows * CELL + 4, 5),
    ]),
    part(
      "path",
      cells.slice(1).map((c, i) => {
        const a = cells[i]!;
        return s.line("wm-path", [a.x + W / 2, a.y + D / 2, 0.3], [c.x + W / 2, c.y + D / 2, 0.3]);
      }),
    ),
  ];
  return (
    <figure className="wm" data-testid="walk-map">
      <svg
        className="wm-svg"
        viewBox={`0 0 250 ${86 + rows * 44}`}
        aria-hidden="true"
        focusable="false"
        data-detail="low"
      >
        <Parts parts={base} />
        {cells.map((c) => {
          const lit = c.index === current;
          const seen = c.index < current;
          const room: Part[] = [
            part("room", [
              ...s.box(lit ? "teal" : seen ? "slate" : "pale", c.x, c.y, 0, W, D, lit ? 18 : 7),
            ]),
          ];
          return (
            <g
              key={c.stop.key}
              className="wm-room"
              data-testid="walk-map-room"
              data-state={lit ? "here" : seen ? "seen" : "ahead"}
              data-ad-view={c.stop.ad_view}
              onClick={() => onPick(c.index)}
            >
              <Parts parts={room} />
            </g>
          );
        })}
      </svg>
      <figcaption className="wm-caption">
        <strong>
          {here
            ? `Stop ${cells.findIndex((c) => c.index === current) + 1} of ${cells.length} inside`
            : `${cells.length} stops inside`}
        </strong>
        <span>{here ? "You are at the lit one. " : ""}Walking order, not a floor plan.</span>
      </figcaption>
    </figure>
  );
}

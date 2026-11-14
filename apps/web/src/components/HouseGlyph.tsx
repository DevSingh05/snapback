// The small isometric house from the worlds page, drawn inline so nothing loads from another
// host. Every fill is a token (styles/tokens.css), so it follows the light and dark sets.
// It is decoration: aria-hidden, and it never carries a word.

const K = 0.866;
type P = [number, number, number];

// 2:1 isometric projection: x runs down-right, y runs down-left, z is up.
function at([x, y, z]: P): string {
  return `${((x - y) * K).toFixed(1)},${((x + y) * 0.5 - z).toFixed(1)}`;
}
function poly(...points: P[]): string {
  return points.map(at).join(" ");
}

const W = 20; // along x
const D = 16; // along y
const H = 11; // wall height
const R = 8; // ridge above the walls

const LAWN = poly([-5, -5, 0], [25, -5, 0], [25, 21, 0], [-5, 21, 0]);
const SHADE = poly([0, 0, 0], [-4, 0, 0], [-4, D, 0], [0, D, 0]);
const PATH = poly([W, 9.5, 0], [25, 9.5, 0], [25, 13.5, 0], [W, 13.5, 0]);
const WALL_LEFT = poly([0, D, 0], [W, D, 0], [W, D, H], [0, D, H]);
const WALL_RIGHT = poly([W, 0, 0], [W, D, 0], [W, D, H], [W, D / 2, H + R], [W, 0, H]);
const ROOF = poly(
  [-1, D + 1.5, H - 1.5],
  [W + 1, D + 1.5, H - 1.5],
  [W + 1, D / 2, H + R],
  [-1, D / 2, H + R],
);
const WINDOWS = [
  poly([3, D, 4], [8, D, 4], [8, D, 8.5], [3, D, 8.5]),
  poly([12, D, 4], [17, D, 4], [17, D, 8.5], [12, D, 8.5]),
  poly([W, 3, 4], [W, 7, 4], [W, 7, 8.5], [W, 3, 8.5]),
];
const DOOR = poly([W, 9.5, 0], [W, 13.5, 0], [W, 13.5, 7], [W, 9.5, 7]);
const MARK = poly([8, 6, 26], [12, 6, 26], [12, 10, 26], [8, 10, 26]);

interface Props {
  className?: string;
  // Lit windows and the amber scan mark over the roof. Off for empty and error states.
  lit?: boolean;
}

export function HouseGlyph({ className, lit = true }: Props) {
  return (
    <svg
      className={`house${lit ? " house-lit" : ""}${className ? ` ${className}` : ""}`}
      viewBox="-24 -24 52 49"
      aria-hidden="true"
      focusable="false"
    >
      <polygon className="house-lawn" points={LAWN} />
      <polygon className="house-shade" points={SHADE} />
      <polygon className="house-path" points={PATH} />
      <polygon className="house-wall-left" points={WALL_LEFT} />
      <polygon className="house-wall-right" points={WALL_RIGHT} />
      {WINDOWS.map((w) => (
        <polygon key={w} className="house-window" points={w} />
      ))}
      <polygon className="house-door" points={DOOR} />
      <polygon className="house-roof" points={ROOF} />
      {lit ? <polygon className="house-mark" points={MARK} /> : null}
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="wordmark">
      <HouseGlyph className="wordmark-house" />
      SNAPBACK
    </span>
  );
}

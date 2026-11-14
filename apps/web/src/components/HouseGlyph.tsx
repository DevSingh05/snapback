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

const W = 22; // along x
const D = 16; // along y
const H = 10; // wall height
const R = 5; // ridge above the walls: a low pitch, so both slopes show, as on the worlds page
const O = 1.6; // eave overhang
const V = 1.2; // overhang past each gable end
const T = 0.9; // roof thickness
const MID = D / 2;
const EAVE = H - (O * R) / MID; // where the overhanging slope ends
const RIDGE = H + R;
// Height of the roof surface above a point at depth y.
const roofAt = (y: number) => RIDGE - (Math.abs(y - MID) * R) / MID;

const LAWN = poly([-6, -6, 0], [28, -6, 0], [28, 22, 0], [-6, 22, 0]);
const SHADE = poly([0, 0, 0], [-4, 0, 0], [-4, D, 0], [0, D, 0]);
const PATH = poly([W, 9, 0], [28, 9, 0], [28, 13, 0], [W, 13, 0]);
const WALL_LEFT = poly([0, D, 0], [W, D, 0], [W, D, H], [0, D, H]);
const WALL_RIGHT = poly([W, 0, 0], [W, D, 0], [W, D, H], [W, MID, RIDGE], [W, 0, H]);
const ROOF_FAR = poly([-V, -O, EAVE], [W + V, -O, EAVE], [W + V, MID, RIDGE], [-V, MID, RIDGE]);
const ROOF_NEAR = poly(
  [-V, D + O, EAVE],
  [W + V, D + O, EAVE],
  [W + V, MID, RIDGE],
  [-V, MID, RIDGE],
);
const FASCIA = poly(
  [-V, D + O, EAVE],
  [W + V, D + O, EAVE],
  [W + V, D + O, EAVE - T],
  [-V, D + O, EAVE - T],
);
const VERGE = poly(
  [W + V, -O, EAVE],
  [W + V, MID, RIDGE],
  [W + V, D + O, EAVE],
  [W + V, D + O, EAVE - T],
  [W + V, MID, RIDGE - T],
  [W + V, -O, EAVE - T],
);
const CHIMNEY_TOP = RIDGE + 2.4;
const CHIMNEY_LEFT = poly(
  [3, 5.5, roofAt(5.5)],
  [6, 5.5, roofAt(5.5)],
  [6, 5.5, CHIMNEY_TOP],
  [3, 5.5, CHIMNEY_TOP],
);
const CHIMNEY_RIGHT = poly(
  [6, 2.5, roofAt(2.5)],
  [6, 5.5, roofAt(5.5)],
  [6, 5.5, CHIMNEY_TOP],
  [6, 2.5, CHIMNEY_TOP],
);
const CHIMNEY_CAP = poly(
  [3, 2.5, CHIMNEY_TOP],
  [6, 2.5, CHIMNEY_TOP],
  [6, 5.5, CHIMNEY_TOP],
  [3, 5.5, CHIMNEY_TOP],
);
const WINDOWS = [
  poly([3, D, 3.4], [8.5, D, 3.4], [8.5, D, 7.6], [3, D, 7.6]),
  poly([13.5, D, 3.4], [19, D, 3.4], [19, D, 7.6], [13.5, D, 7.6]),
  poly([W, 2.6, 3.4], [W, 6.4, 3.4], [W, 6.4, 7.6], [W, 2.6, 7.6]),
];
const DOOR = poly([W, 9, 0], [W, 13, 0], [W, 13, 6.8], [W, 9, 6.8]);

interface Props {
  className?: string;
  // Lit windows. Off for empty and error states.
  lit?: boolean;
}

export function HouseGlyph({ className, lit = true }: Props) {
  return (
    <svg
      className={`house${lit ? " house-lit" : ""}${className ? ` ${className}` : ""}`}
      viewBox="-25 -17 55 43"
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
      <polygon className="house-roof-far" points={ROOF_FAR} />
      <polygon className="house-roof" points={ROOF_NEAR} />
      <polygon className="house-fascia" points={FASCIA} />
      <polygon className="house-verge" points={VERGE} />
      <polygon className="house-wall-left" points={CHIMNEY_LEFT} />
      <polygon className="house-wall-right" points={CHIMNEY_RIGHT} />
      <polygon className="house-path" points={CHIMNEY_CAP} />
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

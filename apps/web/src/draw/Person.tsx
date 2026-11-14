import { makeScene, type Origin, type P3, type Prim } from "./kit";
import "./draw.css";

// A person standing in a drawn scene, in the kit's own isometric look: a head, a teal torso, two
// legs, arms holding a small camera up in front, and a soft contact shadow under the feet. It
// stands at (x, y) on the floor and faces `facing` degrees in the floor plane (0 looks down +x,
// 90 down +y, 180 down -x). The drawn walk uses it as "You are here"; any 3D view can reuse it.
//
// ONE RIGID FIGURE  every part is drawn in place, in one group, and nothing inside it moves on
// its own: move, fade or step the figure in with one transform on this group (or a parent),
// never on a part, so the parts stay joined at every frame.
//
// DEPTH  the figure is drawn far to near within itself. In a scene, draw it after anything
// behind it and before anything in front of it (larger x + y over the same screen span).

/** Height of the figure in scene units at size 1. */
export const PERSON_HEIGHT = 60;

interface Props {
  origin: Origin;
  x: number;
  y: number;
  /** Which way the person faces in the floor plane, degrees. */
  facing?: number;
  /** Scale of the figure; 1 is about two fifths of a drawn room's wall height. */
  size?: number;
  className?: string;
}

function Prims({ prims }: { prims: Prim[] }) {
  return (
    <>
      {prims.map((p, i) =>
        p.k === "poly" ? (
          <polygon key={i} className={p.c} points={p.pts} />
        ) : p.k === "line" ? (
          <line key={i} className={p.c} x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} />
        ) : (
          <circle key={i} className={p.c} cx={p.cx} cy={p.cy} r={p.r} />
        ),
      )}
    </>
  );
}

/** The figure's shapes, far to near, in scene coordinates. Pure, so it can be tested. */
export function personPrims(origin: Origin, x: number, y: number, facing = 180, size = 1): Prim[] {
  const s = makeScene(origin);
  const rad = (facing * Math.PI) / 180;
  const f: [number, number] = [Math.cos(rad), Math.sin(rad)];
  const side: [number, number] = [-f[1], f[0]];
  const u = (n: number) => n * size;
  /** A point on the person: `fwd` ahead, `sd` to the side, `z` up, in figure units. */
  const at = (fwd: number, sd: number, z: number): P3 => [
    x + u(f[0] * fwd + side[0] * sd),
    y + u(f[1] * fwd + side[1] * sd),
    u(z),
  ];
  const depth = (p: P3) => p[0] + p[1];

  // The shadow: a soft pool on the floor under the feet, cast a little away from the light.
  const pool = Array.from({ length: 10 }, (_, i): P3 => {
    const a = (i * Math.PI) / 5;
    return [x + u(2 + Math.cos(a) * 10), y + u(2 + Math.sin(a) * 10), 0.2];
  });
  const shadow = s.poly("dk-contact dk-person-shadow", ...pool);

  // Legs: two short posts from the floor to the hips, the nearer one drawn last.
  const leg = (sd: number): Prim[] => {
    const [lx, ly] = at(0, sd, 0);
    return s.box("dark", lx - u(2.4), ly - u(2.4), 0, u(4.8), u(4.8), u(26));
  };
  const legs = [-3.4, 3.4]
    .map((sd) => ({ sd, d: depth(at(0, sd, 0)) }))
    .sort((a, b) => a.d - b.d)
    .flatMap(({ sd }) => leg(sd));

  // The torso: a teal block from the hips to the shoulders.
  const torso = s.box("teal", x - u(5.5), y - u(5.5), u(26), u(11), u(11), u(20));

  // Arms: from each shoulder down to the elbow, then up to a small camera held before the face.
  const limb = (a: P3, b: P3) => s.line("dk-limb", a, b);
  const arm = (sd: number): Prim[] => [
    limb(at(0, sd * 6.5, 44), at(5, sd * 7.5, 36)),
    limb(at(5, sd * 7.5, 36), at(9, sd * 2.2, 45)),
  ];
  const camera = s.box("dark", ...cameraBox(at(10, 0, 42), u));
  const arms = [...arm(-1), ...arm(1)];

  // The head: one round shape over the shoulders, with a small lit spot.
  const head = [s.dot("dk-head", at(0, 0, 53), u(7)), s.dot("dk-head-lit", at(-1, -2, 56), u(2.4))];

  // The camera and the hands are on the far side when the figure faces away from the viewer
  // (who stands at +x, +y), and on the near side when it faces toward them.
  const away = f[0] + f[1] < 0;
  return away
    ? [shadow, ...camera, ...arms, ...legs, ...torso, ...head]
    : [shadow, ...legs, ...torso, ...head, ...arms, ...camera];
}

/** A small camera body centred on `c`, as box arguments (x, y, z, w, d, h). */
function cameraBox(
  c: P3,
  u: (n: number) => number,
): [number, number, number, number, number, number] {
  return [c[0] - u(3), c[1] - u(3), c[2] - u(2.5), u(6), u(6), u(5)];
}

export function Person({ origin, x, y, facing = 180, size = 1, className }: Props) {
  return (
    <g className={`dk-person ${className ?? ""}`.trim()} data-testid="person">
      <Prims prims={personPrims(origin, x, y, facing, size)} />
    </g>
  );
}

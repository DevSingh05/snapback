import type { CSSProperties } from "react";

import { makeScene, project, type Origin, type P3, type Prim } from "./kit";
import "./draw.css";

// A person standing in a drawn scene, in the kit's own isometric look: a head, a teal torso,
// arms holding a camera up in front, two legs and a soft contact shadow. It stands at (x, y) on
// the floor and faces `facing` degrees in the floor plane (0 looks down +x, 90 down +y, 180 down
// -x). The drawn walk uses it as "You are here"; any 3D view can reuse it.
//
// TURNING  the figure turns about its own vertical axis with the CSS variable `--turn` (an
//          angle) set on any ancestor. A turn about a vertical axis is, on screen, a squash to
//          the floor plane, a rotation, and the squash undone; each layer turns about the axis
//          at its own height, so the head stays over the feet. With no `--turn` it stands still.

/** Screen squash of the 2:1 isometric floor plane: sin 30 deg / cos 30 deg. */
export const ISO_SQUASH = 0.577;

const HEIGHT = 54;

interface Props {
  origin: Origin;
  x: number;
  y: number;
  /** Which way the person faces in the floor plane, degrees. */
  facing?: number;
  /** Scale of the figure; 1 is about a third of a drawn room's wall height. */
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

export function Person({ origin, x, y, facing = 180, size = 1, className }: Props) {
  const s = makeScene(origin);
  const rad = (facing * Math.PI) / 180;
  const f: [number, number] = [Math.cos(rad), Math.sin(rad)];
  const side: [number, number] = [-f[1], f[0]];
  const u = (n: number) => n * size;
  /** A point on the person: `fwd` ahead, `sd` to the side, `z` up, all in figure units. */
  const at = (fwd: number, sd: number, z: number): P3 => [
    x + u(f[0] * fwd + side[0] * sd),
    y + u(f[1] * fwd + side[1] * sd),
    u(z),
  ];
  const axis = (z: number): CSSProperties => {
    const [ax, ay] = project([x, y, u(z)], origin);
    return { transformOrigin: `${ax.toFixed(1)}px ${ay.toFixed(1)}px` };
  };

  // The shadow: a soft eight-sided pool on the floor, cast a little away from the light.
  const pool = Array.from({ length: 8 }, (_, i): P3 => {
    const a = (i * Math.PI) / 4;
    return [x + u(3 + Math.cos(a) * 9), y + u(3 + Math.sin(a) * 9), 0.1];
  });
  const legs = [
    s.line("dk-limb", at(0, -2.6, 25), at(0.6, -3.4, 0)),
    s.line("dk-limb", at(0, 2.6, 25), at(-0.6, 3.4, 0)),
  ];
  const feet = [
    s.line("dk-limb dk-foot", at(0.6, -3.4, 0.4), at(4, -3.4, 0.4)),
    s.line("dk-limb dk-foot", at(-0.6, 3.4, 0.4), at(3, 3.4, 0.4)),
  ];
  // Arms: shoulder, elbow out, both hands meeting at a small camera held in front of the face.
  const arms = [
    s.line("dk-limb", at(0, -5.4, 41), at(4.5, -6.5, 34)),
    s.line("dk-limb", at(4.5, -6.5, 34), at(8.5, -1.6, 43)),
    s.line("dk-limb", at(0, 5.4, 41), at(4.5, 6.5, 34)),
    s.line("dk-limb", at(4.5, 6.5, 34), at(8.5, 1.6, 43)),
  ];
  const camera = [
    s.poly("dk-person-cam", at(8.5, -3, 40), at(8.5, 3, 40), at(8.5, 3, 46), at(8.5, -3, 46)),
  ];
  const torso = s.box("teal", x - u(3.5), y - u(4.5), u(24), u(7), u(9), u(18));
  const head = [
    s.dot("dk-head", at(0, 0, 50), u(5.6)),
    s.dot("dk-head-lit", at(-0.8, -1.4, 52), u(2)),
  ];

  const facesAway = f[0] + f[1] < 0; // the viewer stands at +x, +y
  return (
    <g className={`dk-person ${className ?? ""}`.trim()} data-testid="person" data-height={HEIGHT}>
      <polygon
        className="dk-contact dk-person-shadow"
        points={(s.poly("", ...pool) as { pts: string }).pts}
      />
      <g className="dk-person-turn" style={axis(12)}>
        <Prims prims={[...feet, ...legs]} />
      </g>
      {facesAway && (
        <g className="dk-person-turn" style={axis(40)}>
          <Prims prims={[...camera, ...arms]} />
        </g>
      )}
      <g className="dk-person-turn" style={axis(33)}>
        <Prims prims={torso} />
      </g>
      {!facesAway && (
        <g className="dk-person-turn" style={axis(40)}>
          <Prims prims={[...arms, ...camera]} />
        </g>
      )}
      <g className="dk-person-turn" style={axis(50)}>
        <Prims prims={head} />
      </g>
    </g>
  );
}

import { Parts } from "../draw/Parts";
import { between, makeScene, part, project, type P3, type Part } from "../draw/kit";
import { drawRoom } from "../walk/rooms";
import { HouseGlyph } from "./HouseGlyph";

// Small drawings in the kit's style for the screens around the walk: what a check is about
// (the place, the person, the price, the ad), an apartment block for a researched place and a
// clipboard for the tour prep. Decoration only: hidden from readers, never the only carrier of
// a fact. Each is a stand-in drawing, not a picture of any real home.

const s = makeScene({ ox: 0, oy: 0 });

// The person check: a front door in a short run of wall, with a mat.
const DOOR: Part[] = [
  part("ground", [s.onZ("dk-path", 0, -14, -8, 44, 66)]),
  part("mat", [s.onZ("dk-asphalt", 0.2, 9, 12, 14, 26)], true),
  part("wall", [s.contact(0, 0, 8, 50, 7), ...s.box("white", 0, 0, 0, 8, 50, 62)]),
  part("siding", s.coursesX(8.2, 0, 50, 0, 62, 6), true),
  ...s.doorX(8, 12, 38, 50, 1.8),
  part("lamp", s.box("teal", 8, 42, 40, 2, 4, 6), true),
];

// The price check: a price tag lying flat, with a stack of coins beside it.
const TAG: Part[] = [
  part("tag", [s.contact(0, 0, 64, 40, 6), ...s.box("white", 0, 0, 0, 64, 40, 4)]),
  part("price", s.box("teal", 8, 8, 4, 30, 12, 2)),
  part(
    "lines",
    [24, 30].map((y, i) => s.onZ("ka-text", 4.2, 8, y, i ? 26 : 44, 3)),
    true,
  ),
  part("hole", [s.onZ("dk-asphalt", 4.2, 52, 6, 6, 6)], true),
  ...[0, 1, 2].map((i) => part("coin", s.box("metal", 70, 14, i * 5, 16, 16, 4))),
];

// What the ad claims: the ad as it was sent, three photos and lines of text.
const AD: Part[] = [
  part("card", [s.contact(0, 0, 62, 84, 7), ...s.box("white", 0, 0, 0, 62, 84, 4)]),
  part("photos", [
    s.onZ("dk-glass", 4.2, 6, 6, 50, 26),
    s.onZ("ka-thumb", 4.2, 6, 36, 23, 16),
    s.onZ("ka-thumb", 4.2, 33, 36, 23, 16),
  ]),
  part(
    "text",
    [58, 65, 72].map((y, i) => s.onZ("ka-text", 4.2, 6, y, i === 2 ? 30 : 50, 3)),
    true,
  ),
];

// A researched apartment building: a block with rows of windows and a flat roof on a lot.
const TW = 56;
const TD = 44;
const TH = 104;
const FLOORS = between(0, TH, 5);
const TOWER: Part[] = [
  part("lot", [s.onZ("dk-lawn", 0, -18, -14, TW + 40, TD + 34)]),
  part("walk", [s.onZ("dk-path", 0.1, TW, 14, 22, 14)]),
  part("block", [s.contact(0, 0, TW, TD, 20), ...s.box("pale", 0, 0, 0, TW, TD, TH)]),
  ...FLOORS.flatMap((z) => [
    ...between(0, TW, 3).flatMap((x) => s.windowY(TD, x - 5, x + 5, z - 6, z + 5, 1)),
    ...between(0, TD, 2).flatMap((y) => s.windowX(TW, y - 5, y + 5, z - 6, z + 5, 1)),
  ]),
  ...s.doorX(TW, 15, 27, 13, 1.2),
  ...s.flatRoof("white", 0, 0, TH, TW, TD, 3),
  part("roof-unit", s.box("metal", 12, 12, TH + 2, 14, 12, 6), true),
  s.shrub(4, TD + 2, 22, 6, 5),
  s.tree(-8, 34, 1.6),
];

// The tour prep: a clipboard with a ticked list.
const BOARD: Part[] = [
  part("board", [s.contact(0, 0, 60, 84, 7), ...s.box("wood", 0, 0, 0, 60, 84, 3)]),
  part("sheet", [s.onZ("dk-trim", 3.2, 5, 9, 50, 70)]),
  part("clip", s.box("metal", 20, 2, 3, 20, 9, 3)),
  ...[22, 36, 50, 64].flatMap((y, i) => [
    part("tick", s.box(i < 3 ? "teal" : "pale", 10, y, 3.2, 7, 7, 1.4)),
    part("line", [s.onZ("ka-text", 3.4, 21, y + 2, i === 3 ? 20 : 30, 3)], true),
  ]),
];

// The product's own mark: the ad's photos pinned to the spot they were taken from. `pinned`
// is a home on its lot with two photos traced to it; `scan` is a room with one photo pinned
// where its camera stood. Both are drawings, labelled as stand-ins where they sit by a claim.
const HOME: Part[] = [
  part("lot", [s.onZ("ka-lot", 0.3, -18, -16, 138, 116)]),
  part("drive", [s.onZ("dk-path", 0.35, 102, 34, 18, 22)]),
  ...s.house(0, 0, 100, 80, 40, "white", "teal"),
  s.shrub(6, 82, 30, 7, 6),
  s.tree(-10, 70, 1.8),
];
const ROOM = drawRoom("living");
const ROOM_O = { ox: 400, oy: 196 };

interface Photo {
  x: number;
  y: number;
  w: number;
  to: P3;
}
const PINNED: Photo[] = [
  { x: -166, y: -78, w: 62, to: [30, 80, 20] },
  { x: 62, y: -124, w: 62, to: [100, 46, 16] },
];
const SCANNED: Photo[] = [{ x: 122, y: 34, w: 178, to: [150, 168, 0] }];

function Photos({ list, origin }: { list: Photo[]; origin: { ox: number; oy: number } }) {
  return (
    <>
      {list.map((p, i) => {
        const h = p.w * 0.7;
        const m = p.w * 0.065;
        const [tx, ty] = project(p.to, origin);
        const pin = p.w * 0.06;
        return (
          <g key={i} className="ka-photo" style={{ animationDelay: `${0.5 + i * 0.16}s` }}>
            <line
              className="ka-trace"
              x1={p.x + p.w / 2}
              y1={p.y + h}
              x2={tx}
              y2={ty}
              pathLength={1}
            />
            <rect className="ka-pin" x={tx - pin} y={ty - pin} width={pin * 2} height={pin * 2} />
            <rect className="ka-mat" x={p.x} y={p.y} width={p.w} height={h} />
            <rect
              className="ka-pic"
              x={p.x + m}
              y={p.y + m}
              width={p.w - m * 2}
              height={h - m * 2}
            />
            <rect
              className="ka-pic-floor"
              x={p.x + m}
              y={p.y + h * 0.68}
              width={p.w - m * 2}
              height={h * 0.32 - m}
            />
            <rect
              className="ka-pic-thing"
              x={p.x + p.w * (0.2 + i * 0.14)}
              y={p.y + h * 0.34}
              width={p.w * 0.3}
              height={h * 0.4}
            />
          </g>
        );
      })}
    </>
  );
}

const ART = {
  person: { parts: DOOR, box: "-52 -62 84 104" },
  price: { parts: TAG, box: "-40 -14 122 82" },
  claims: { parts: AD, box: "-80 -12 142 92" },
  apartment: { parts: TOWER, box: "-66 -116 136 196" },
  prep: { parts: BOARD, box: "-80 -10 140 90" },
} as const;

export type KitArtKind = keyof typeof ART | "house" | "pinned" | "scan";

interface Props {
  kind: KitArtKind;
  className?: string;
  // "low" drops the fine detail, for small sizes.
  detail?: "full" | "low";
  // Lit windows on the house. Off for empty and error states.
  lit?: boolean;
}

export function KitArt({ kind, className, detail = "full", lit = true }: Props) {
  const cls = `kit-art kit-art-${kind}${className ? ` ${className}` : ""}`;
  if (kind === "house") return <HouseGlyph className={cls} detail={detail} lit={lit} />;
  const low = detail === "low" ? "low" : undefined;
  if (kind === "pinned")
    return (
      <svg
        className={cls}
        viewBox="-172 -130 304 232"
        data-detail={low}
        aria-hidden="true"
        focusable="false"
      >
        <g className="ka-lit">
          <Parts parts={HOME} />
        </g>
        <Photos list={PINNED} origin={{ ox: 0, oy: 0 }} />
      </svg>
    );
  if (kind === "scan")
    return (
      <svg
        className={cls}
        viewBox="110 20 580 500"
        data-detail={low}
        aria-hidden="true"
        focusable="false"
      >
        <Parts parts={ROOM.base} />
        <Parts parts={ROOM.things} />
        <Photos list={SCANNED} origin={ROOM_O} />
      </svg>
    );
  const art = ART[kind];
  return (
    <svg className={cls} viewBox={art.box} data-detail={low} aria-hidden="true" focusable="false">
      <Parts parts={art.parts} />
    </svg>
  );
}

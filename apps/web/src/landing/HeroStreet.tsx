import { Parts } from "../draw/Parts";
import { between, makeScene, part, project, type Part } from "../draw/kit";
import "./landing.css";

// The first screen's scene, built with the drawing kit: a small street of homes, one of them
// lit, with three photos from an ad traced back to it. Decoration only (aria-hidden): it shows
// what the product does and carries no data.

const ORIGIN = { ox: 236, oy: 96 };
const s = makeScene(ORIGIN);

const street = (y: number): Part[] => [
  part("pavement", [
    s.onZ("dk-path", 0.05, -120, y - 10, 520, 10),
    s.onZ("dk-path", 0.05, -120, y + 40, 520, 10),
  ]),
  part("street", [s.onZ("dk-asphalt", 0.05, -120, y, 520, 40)]),
  part(
    "street-lines",
    between(-120, 400, 15).map((x) => s.line("dk-paint", [x, y + 20, 0.2], [x + 14, y + 20, 0.2])),
    true,
  ),
];

// The lit home sits mid-row; its lot is ringed and its roof is lit.
const HOME = { x: 96, y: 62, w: 74, d: 56, h: 28 };

const FAR: Part[] = [
  part("ground", [s.onZ("dk-lawn", 0, -120, -90, 520, 420)]),
  s.tree(-64, 20, 1.6),
  ...s.house(-40, 66, 62, 50, 24, "pale"),
  s.tree(40, 54, 1.5),
];
const NEAR: Part[] = [
  s.tree(188, 60, 1.6),
  ...s.house(206, 68, 62, 50, 24, "pale"),
  s.tree(286, 92, 1.4),
  ...street(138),
  s.car("pale", 20, 144),
  s.car("slate", 226, 160),
  ...s.house(-30, 204, 64, 50, 24, "pale"),
  s.tree(60, 214, 1.7),
  ...s.house(150, 206, 64, 50, 24, "pale"),
  s.tree(246, 220, 1.5),
];
const LOT: Part[] = [
  part("lot", [s.onZ("hs-lot", 0.3, HOME.x - 16, HOME.y - 14, HOME.w + 34, HOME.d + 34)]),
];
const LIT: Part[] = [
  part("drive", [s.onZ("dk-path", 0.35, HOME.x + HOME.w + 2, HOME.y + 28, 14, 46)]),
  ...s.house(HOME.x, HOME.y, HOME.w, HOME.d, HOME.h, "white", "teal"),
  s.shrub(HOME.x + 4, HOME.y + HOME.d + 2, 26, 6, 5),
];

// Three ad photos, floating above the street, each traced to a spot on the lit home.
const PHOTOS = [
  { x: 26, y: 18, to: [HOME.x + 20, HOME.y + HOME.d, 16] as const },
  { x: 118, y: 4, to: [HOME.x + 54, HOME.y + HOME.d, 16] as const },
  { x: 210, y: 22, to: [HOME.x + HOME.w, HOME.y + 38, 12] as const },
];
const PW = 62;
const PH = 44;

export function HeroStreet({ className }: { className?: string }) {
  return (
    <svg
      className={`hs${className ? ` ${className}` : ""}`}
      viewBox="64 -4 344 262"
      aria-hidden="true"
      focusable="false"
    >
      <Parts parts={FAR} />
      <Parts parts={LOT} />
      <g className="hs-lit">
        <Parts parts={LIT} />
      </g>
      <Parts parts={NEAR} />
      {PHOTOS.map((p, i) => {
        const [tx, ty] = project([...p.to], ORIGIN);
        return (
          <g key={i} className="hs-photo" style={{ animationDelay: `${0.25 + i * 0.16}s` }}>
            <line
              className="hs-trace"
              x1={p.x + PW / 2}
              y1={p.y + PH}
              x2={tx}
              y2={ty}
              pathLength={1}
              style={{ animationDelay: `${0.6 + i * 0.16}s` }}
            />
            <rect className="hs-pin" x={tx - 3.5} y={ty - 3.5} width={7} height={7} />
            <rect className="hs-mat" x={p.x} y={p.y} width={PW} height={PH} />
            <rect className="hs-pic" x={p.x + 4} y={p.y + 4} width={PW - 8} height={PH - 8} />
            <rect
              className="hs-pic-floor"
              x={p.x + 4}
              y={p.y + PH - 14}
              width={PW - 8}
              height={10}
            />
            <rect
              className="hs-pic-thing"
              x={p.x + 12 + i * 8}
              y={p.y + 14}
              width={18}
              height={18}
            />
          </g>
        );
      })}
    </svg>
  );
}

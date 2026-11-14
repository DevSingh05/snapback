import type { CSSProperties } from "react";

import { HouseGlyph } from "../components/HouseGlyph";
import type { TourPlan, TourStop } from "../contracts";
import { boxFaces, points, project, type Box, type Origin } from "./iso";
import "./walk.css";

// The fixture stage: a team-made cutaway of one room, drawn in code, standing in for the live
// Matterport scan. It carries no sponsor imagery and says so on screen. In a live walk the scan
// itself fills the stage and StageCaption sits over it.

const O: Origin = { ox: 400, oy: 196 };
const SIZE = 300;
const WALL_H = 150;

// Where the ad photo lands: on the left wall, clear of the furniture.
const PHOTO = { y0: 60, y1: 180, z0: 68, z1: 140 };
const CAMERA: [number, number, number] = [252, 122, 0];

type RoomKind = "kitchen" | "bathroom" | "bedroom" | "living" | "entry" | "plain";

function roomKind(stop: TourStop): RoomKind {
  const name = `${stop.room_label ?? ""} ${stop.title}`.toLowerCase();
  if (name.includes("kitchen")) return "kitchen";
  if (name.includes("bath")) return "bathroom";
  if (name.includes("bed")) return "bedroom";
  if (name.includes("living")) return "living";
  if (stop.kind === "door" || name.includes("entry")) return "entry";
  return "plain";
}

// Furniture, far to near. Heights on the left wall stay under the photo.
const FURNITURE: Record<RoomKind, Box[]> = {
  kitchen: [
    { x: 40, y: 0, w: 170, d: 42, h: 58, tone: "slate" },
    { x: 40, y: 0, z: 58, w: 170, d: 44, h: 5, tone: "white" },
    { x: 226, y: 0, w: 54, d: 48, h: 124, tone: "pale" },
    { x: 0, y: 70, w: 40, d: 150, h: 56, tone: "slate" },
    { x: 0, y: 70, z: 56, w: 42, d: 150, h: 5, tone: "white" },
    { x: 130, y: 140, w: 112, d: 52, h: 56, tone: "pale" },
    { x: 126, y: 136, z: 56, w: 120, d: 60, h: 5, tone: "white" },
  ],
  bathroom: [
    { x: 120, y: 0, w: 96, d: 38, h: 56, tone: "slate" },
    { x: 118, y: 0, z: 56, w: 100, d: 40, h: 5, tone: "white" },
    { x: 236, y: 0, w: 38, d: 50, h: 34, tone: "white" },
    { x: 0, y: 40, w: 64, d: 176, h: 42, tone: "white" },
    { x: 8, y: 48, z: 42, w: 48, d: 160, h: 2, tone: "pale" },
  ],
  bedroom: [
    { x: 70, y: 0, w: 150, d: 14, h: 70, tone: "slate" },
    { x: 70, y: 14, w: 150, d: 170, h: 30, tone: "white" },
    { x: 80, y: 20, z: 30, w: 58, d: 34, h: 9, tone: "pale" },
    { x: 152, y: 20, z: 30, w: 58, d: 34, h: 9, tone: "pale" },
    { x: 70, y: 100, z: 30, w: 150, d: 84, h: 4, tone: "slate" },
    { x: 232, y: 0, w: 40, d: 40, h: 40, tone: "pale" },
    { x: 0, y: 200, w: 36, d: 70, h: 52, tone: "pale" },
  ],
  living: [
    { x: 50, y: 0, w: 176, d: 16, h: 72, tone: "slate" },
    { x: 50, y: 16, w: 176, d: 44, h: 40, tone: "slate" },
    { x: 60, y: 22, z: 40, w: 156, d: 36, h: 8, tone: "pale" },
    { x: 108, y: 126, w: 84, d: 54, h: 26, tone: "white" },
    { x: 0, y: 216, w: 30, d: 30, h: 30, tone: "pale" },
    { x: 6, y: 222, z: 30, w: 18, d: 18, h: 34, tone: "green" },
  ],
  entry: [
    { x: 196, y: 0, w: 84, d: 30, h: 62, tone: "pale" },
    { x: 0, y: 200, w: 30, d: 60, h: 36, tone: "slate" },
  ],
  plain: [{ x: 120, y: 0, w: 110, d: 40, h: 50, tone: "pale" }],
};

const RUG: Partial<Record<RoomKind, [number, number, number, number]>> = {
  living: [70, 96, 150, 120],
  bedroom: [40, 196, 210, 70],
  bathroom: [96, 70, 96, 60],
  entry: [80, 60, 120, 80],
};

function Room({ kind, cone }: { kind: RoomKind; cone: boolean }) {
  const rug = RUG[kind];
  return (
    <g className="rs-room">
      <polygon
        className="rs-floor"
        points={points(O, [0, 0, 0], [SIZE, 0, 0], [SIZE, SIZE, 0], [0, SIZE, 0])}
      />
      <polygon
        className="rs-wall-left"
        points={points(O, [0, 0, 0], [0, SIZE, 0], [0, SIZE, WALL_H], [0, 0, WALL_H])}
      />
      <polygon
        className="rs-wall-right"
        points={points(O, [0, 0, 0], [SIZE, 0, 0], [SIZE, 0, WALL_H], [0, 0, WALL_H])}
      />
      {kind === "entry" && (
        <polygon
          className="rs-door"
          points={points(O, [90, 0, 0], [150, 0, 0], [150, 0, 118], [90, 0, 118])}
        />
      )}
      {kind !== "entry" && (
        <polygon
          className="rs-window"
          points={
            kind === "bathroom"
              ? points(O, [128, 0, 78], [206, 0, 78], [206, 0, 128], [128, 0, 128])
              : points(O, [70, 0, 84], [180, 0, 84], [180, 0, 134], [70, 0, 134])
          }
        />
      )}
      {rug && (
        <polygon
          className="rs-rug"
          points={points(
            O,
            [rug[0], rug[1], 0],
            [rug[0] + rug[2], rug[1], 0],
            [rug[0] + rug[2], rug[1] + rug[3], 0],
            [rug[0], rug[1] + rug[3], 0],
          )}
        />
      )}
      {cone && (
        <polygon
          className="rs-cone"
          points={points(O, CAMERA, [0, PHOTO.y1, 0], [0, PHOTO.y0, 0])}
        />
      )}
      {FURNITURE[kind].map((b, i) => {
        const f = boxFaces(b, O);
        return (
          <g key={i} className={`rs-box rs-${b.tone ?? "pale"}`}>
            <polygon className="rs-face-left" points={f.left} />
            <polygon className="rs-face-right" points={f.right} />
            <polygon className="rs-face-top" points={f.top} />
          </g>
        );
      })}
    </g>
  );
}

const W = PHOTO.y1 - PHOTO.y0;
const H = PHOTO.z1 - PHOTO.z0;
const [LAND_X, LAND_Y] = project([0, PHOTO.y1, PHOTO.z1], O);
const LAND = {
  "--rs-x": `${LAND_X.toFixed(1)}px`,
  "--rs-y": `${LAND_Y.toFixed(1)}px`,
} as CSSProperties;

const CAMERA_FACES = boxFaces(
  { x: CAMERA[0] - 6, y: CAMERA[1] - 6, w: 12, d: 12, h: 46, tone: "door" },
  O,
);

function LandedPhoto({ alias, fly }: { alias: string; fly: boolean }) {
  return (
    <>
      <g className="rs-box rs-camera">
        <polygon className="rs-face-left" points={CAMERA_FACES.left} />
        <polygon className="rs-face-right" points={CAMERA_FACES.right} />
        <polygon className="rs-face-top" points={CAMERA_FACES.top} />
      </g>
      <g
        className="rs-photo"
        data-testid="stage-photo"
        data-fly={fly ? "true" : undefined}
        style={LAND}
      >
        <rect className="rs-photo-mat" x={-6} y={-6} width={W + 12} height={H + 12} />
        <rect className="rs-photo-wall" x={0} y={0} width={W} height={H} />
        <rect className="rs-photo-floor" x={0} y={H - 18} width={W} height={18} />
        <rect className="rs-photo-window" x={12} y={10} width={34} height={26} />
        <rect className="rs-photo-block" x={60} y={30} width={48} height={H - 30 - 10} />
        <rect className="rs-photo-tag" x={-6} y={-24} width={34} height={18} />
        <text className="rs-photo-tag-text mono" x={11} y={-11} textAnchor="middle">
          {alias}
        </text>
      </g>
    </>
  );
}

function MissingFrame() {
  return (
    <g className="rs-missing" data-testid="stage-missing" style={LAND}>
      <rect className="rs-missing-frame" x={-6} y={-6} width={W + 12} height={H + 12} />
    </g>
  );
}

interface Props {
  stop: TourStop;
  plan: TourPlan;
  reduced: boolean;
  /** The evidence alias of the ad photo placed at this stop, if one was. */
  photoAlias?: string | null;
  /** True when the ad showed no photo of this room. */
  unshown?: boolean;
}

export function StopStage({ stop, plan, reduced, photoAlias, unshown = false }: Props) {
  const outside = stop.kind === "arrive" || stop.kind === "outro";
  return (
    <div
      className="rs"
      data-testid="tour-placeholder"
      data-motion={reduced ? "reduced" : "full"}
      data-kind={outside ? "outside" : roomKind(stop)}
      role="img"
      aria-label={`${stop.title}. A drawing made by the team, standing in for the 3D scan.`}
    >
      {outside ? (
        <div className="rs-outside">
          <HouseGlyph className="rs-house" lit={false} />
          {stop.kind === "arrive" && plan.aerial?.captured_on && (
            <span className="rs-aerial-date mono">
              Aerial photo captured {plan.aerial.captured_on}
            </span>
          )}
        </div>
      ) : (
        <svg className="rs-svg" viewBox="0 0 800 520" aria-hidden="true" focusable="false">
          <g className="rs-sway">
            <polygon
              className="rs-ground"
              points={points(
                O,
                [-26, -26, -8],
                [SIZE + 26, -26, -8],
                [SIZE + 26, SIZE + 26, -8],
                [-26, SIZE + 26, -8],
              )}
            />
            <Room kind={roomKind(stop)} cone={Boolean(photoAlias)} />
            {photoAlias && <LandedPhoto alias={photoAlias} fly={!reduced} />}
            {!photoAlias && unshown && <MissingFrame />}
          </g>
        </svg>
      )}
      <span className="rs-standin mono">Drawn stand-in (fixture)</span>
    </div>
  );
}

interface CaptionProps {
  stop: TourStop;
  photoAlias?: string | null;
  unshown?: boolean;
}

/** One line over the stage, in the live scan and the fixture alike. */
export function StageCaption({ stop, photoAlias, unshown = false }: CaptionProps) {
  if (stop.kind !== "room" && stop.kind !== "stop") return null;
  if (photoAlias)
    return (
      <p className="rs-caption rs-caption-placed" data-testid="stage-caption">
        <strong>Taken here{stop.room_label ? `: ${stop.room_label}` : ""}</strong>
        <span>
          Your ad photo <span className="mono">{photoAlias}</span>, back where it was taken in this
          scan.
        </span>
      </p>
    );
  if (unshown)
    return (
      <p className="rs-caption rs-caption-unshown" data-testid="stage-caption">
        <span className="rs-caption-dash" aria-hidden="true" />
        <strong>The ad showed no photo of this room.</strong>
        <span>See it yourself before you pay anything.</span>
      </p>
    );
  return null;
}

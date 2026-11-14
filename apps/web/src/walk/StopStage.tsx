import { useMemo, type CSSProperties } from "react";

import { HouseGlyph } from "../components/HouseGlyph";
import type { TourPlan, TourStop } from "../contracts";
import { points, project } from "./iso";
import { Parts } from "../draw/Parts";
import { O, SIZE, box } from "./roomParts";
import { drawRoom, roomKind, type RoomKind } from "./rooms";
import "./walk.css";

// The fixture stage: a team-made cutaway of one room, drawn in code, standing in for the live
// Matterport scan. It carries no sponsor imagery and says so on screen. In a live walk the scan
// itself fills the stage and StageCaption sits over it.

// Where the ad photo lands: on the left wall, clear of the furniture.
const PHOTO = { y0: 60, y1: 180, z0: 68, z1: 140 };
const CAMERA: [number, number, number] = [252, 122, 0];

function Room({ kind, cone }: { kind: RoomKind; cone: boolean }) {
  const room = useMemo(() => drawRoom(kind), [kind]);
  return (
    <g className="rs-room">
      <Parts parts={room.base} />
      {cone && (
        <polygon
          className="rs-cone"
          points={points(O, CAMERA, [0, PHOTO.y1, 0], [0, PHOTO.y0, 0])}
        />
      )}
      <Parts parts={room.things} />
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

const CAMERA_POST = [
  { name: "camera", prims: box("teal", CAMERA[0] - 6, CAMERA[1] - 6, 0, 12, 12, 46) },
];

function LandedPhoto({ alias, fly }: { alias: string; fly: boolean }) {
  return (
    <>
      <g className="rs-camera">
        <Parts parts={CAMERA_POST} />
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
  /** False hides the landed photo, to look at the room behind it. */
  photoShown?: boolean;
  /** True when the ad showed no photo of this room. */
  unshown?: boolean;
}

export function StopStage({
  stop,
  plan,
  reduced,
  photoAlias,
  photoShown = true,
  unshown = false,
}: Props) {
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
          <ellipse className="rs-glow" cx={400} cy={420} rx={300} ry={70} />
          <ellipse className="rs-shadow" cx={400} cy={438} rx={250} ry={46} />
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
            {photoAlias && photoShown && <LandedPhoto alias={photoAlias} fly={!reduced} />}
            {!photoAlias && unshown && <MissingFrame />}
          </g>
        </svg>
      )}
      <span className="rs-standin mono">
        {plan.source === "fixture"
          ? "Drawn stand-in (fixture)"
          : "Drawn stand-in. Not this home's real layout."}
      </span>
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

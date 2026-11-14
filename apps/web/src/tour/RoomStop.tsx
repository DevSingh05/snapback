import type { ReactNode } from "react";

import type { TourPlan, TourStop } from "../contracts";
import { floorOf, viewAngles, type LandingState, type UpAxis } from "../twin/landing";

// Structure only: every colour, size and border is a class in tour.css, so a design pass can
// restyle without touching this logic.

/** The source line of a fact. "As of CoStar's last research" goes on CoStar's own lines only: it
 *  would be wrong beside a Vexcel date or a Matterport label. */
export function sourceLine(source: string, asOf: string): string {
  return source.startsWith("CoStar") ? `${source}, ${asOf}` : source;
}

/** What the empty frame says for a stop with no placed ad photo. Null: say nothing. */
export function emptyFrameText(stop: TourStop, plan: TourPlan): string | null {
  if (stop.photos.length > 0) return null;
  if (stop.ad_view === "none_placed") return "The ad showed no photo of this room.";
  const unplaced = plan.coverage?.unplaced ?? 0;
  if (stop.ad_view === "unknown" && unplaced > 0) {
    const n = unplaced === 1 ? "1 photo" : `${unplaced} photos`;
    return `None of the placed photos are from this room (${n} could not be placed).`;
  }
  return null;
}

/** The landing state of a stop's first placed photo, for PhotoLanding. */
export function landingOfStop(stop: TourStop, up: UpAxis = "y"): LandingState | null {
  const photo = stop.photos[0];
  if (!photo || !photo.position) return null;
  const angles = viewAngles(photo);
  if (!angles) return null;
  const { yaw, pitch } = angles;
  return {
    kind: "match",
    photoId: photo.photo_id,
    sweepId: photo.sweep_id ?? "",
    roomLabel: stop.room_label ?? null,
    yaw,
    pitch,
    fovDeg: photo.fov_deg ?? null,
    position: photo.position,
    floor: floorOf(photo.position, up),
  };
}

interface Props {
  stop: TourStop;
  plan: TourPlan;
  /** The director picked this stop to dwell on: open expanded. */
  dwell: boolean;
  showingPhoto: boolean;
  onToggle: () => void;
  /** Set while a placeholder stands in for the ad's own photo: says which, never silent. */
  photoNote?: string | null;
  /** Where the agent rail mounts (the walk's real trace); empty until it exists. */
  rail?: ReactNode;
}

export function RoomStop({ stop, plan, dwell, showingPhoto, onToggle, photoNote, rail }: Props) {
  const empty = emptyFrameText(stop, plan);
  const inside = stop.kind === "room" || stop.kind === "stop";
  const details = (
    <>
      {stop.facts.length > 0 && (
        <ul className="tour-facts" aria-label="What the record says">
          {stop.facts.map((f) => (
            <li key={f.text}>
              {f.text} <span className="tour-src">{sourceLine(f.source, plan.as_of)}</span>
            </li>
          ))}
        </ul>
      )}
      {stop.claims.length > 0 && (
        <ul className="tour-claims" aria-label="What the ad claimed">
          {stop.claims.map((c) => (
            <li key={c.text}>
              {c.text} <span className="tour-src">{sourceLine(c.source, plan.as_of)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
  return (
    <div className="tour-stop" data-kind={stop.kind} data-ad-view={stop.ad_view} data-dwell={dwell}>
      {stop.note && <p className="tour-note">{stop.note}</p>}
      {(stop.kind === "room" || (stop.kind === "door" && !plan.rooms_labelled)) && (
        <p className="tour-note">{plan.rooms_note}</p>
      )}
      {stop.photos.length > 0 && (
        <div className="tour-photo-row">
          <p className="tour-photo-label" data-testid="photo-label">
            The photo you sent, taken here.
          </p>
          <button type="button" aria-pressed={showingPhoto} onClick={onToggle}>
            {showingPhoto ? "Show the scan" : "Show the photo"}
          </button>
        </div>
      )}
      {stop.photos.length > 0 && photoNote && (
        <p className="tour-photo-note" data-testid="photo-fallback">
          {photoNote}
        </p>
      )}
      {empty && (
        <p className="tour-empty-frame" data-testid="empty-frame">
          {empty}
        </p>
      )}
      {inside ? (
        <details className="tour-details" open={dwell || undefined} data-testid="stop-details">
          <summary>{dwell ? "Worth a closer look" : "On record for this room"}</summary>
          {details}
        </details>
      ) : (
        details
      )}
      {stop.tip && (
        <p className="tour-tip">
          <strong>Check this in person:</strong> {stop.tip}
        </p>
      )}
      <div className="tour-agent-slot" data-testid="agent-rail-slot">
        {rail}
      </div>
    </div>
  );
}

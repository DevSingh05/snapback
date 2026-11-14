// The frames around the player (design v4 6.3 ticket 6): the aerial that opens the walk and the
// "On this stop" rows under the stage. Structure only; looks are in tour.css.
import type { TourPlan, TourStop } from "../contracts";
import { Photo } from "../ui/Photo";
import { photoFor } from "../ui/photoFor";
import { seeingLine } from "../walk/seeing";
import { emptyFrameText } from "./RoomStop";

interface AerialProps {
  /** The runtime aerial, as an address on our API (a blob URL). Null: the stock exterior stands in. */
  src: string | null;
  /** The capture date, only when the API returned one. */
  capturedOn?: string | null;
  /** A stable seed (the property or case id) so one building always gets the same stock photo. */
  seed: string;
}

/** The opening frame of the walk: the building from above, under the matte finish, with its place
 *  marked in 1px bone and a stamp. Kit imagery arrives only from the API at runtime; with none
 *  (FIXTURE) the licensed stock exterior shows, stamped SAMPLE PHOTO. */
export function AerialOpening({ src, capturedOn, seed }: AerialProps) {
  const chosen = src
    ? null
    : photoFor({ source: "fixture", stock: "exterior", seed }, "a building seen from outside");
  return (
    <figure
      className="tour-aerial-frame"
      data-testid="aerial-opening"
      data-live={src ? "true" : "false"}
    >
      <Photo
        className="tour-aerial-photo"
        src={src ?? chosen?.src ?? null}
        alt={
          src
            ? "Aerial view of the building"
            : (chosen?.alt ?? "A building seen from outside, a sample photo")
        }
        stamp={src ? "aerial" : "sample"}
        stampNote={src && capturedOn ? capturedOn : undefined}
        hero
        eager
      >
        {/* A marker for where the building sits in the tile, not a surveyed footprint. */}
        <svg
          className="tour-footprint"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
          focusable="false"
        >
          <rect x="36" y="34" width="28" height="32" />
        </svg>
      </Photo>
      {!src && chosen?.credit && <figcaption className="sr-only">{chosen.credit}</figcaption>}
    </figure>
  );
}

/** What the ad showed at this stop, in one plain sentence from the plan's own fields. */
export function adShowedLine(stop: TourStop, plan: TourPlan): string {
  if (stop.photos.length > 0) return "A photo from the ad was taken in this room.";
  const empty = emptyFrameText(stop, plan);
  if (empty) return empty;
  if (stop.kind === "arrive") return "The listing's building, seen from above before you go in.";
  if (stop.kind === "outro") return "Nothing more: that is the whole walk.";
  return "No photo from the ad is placed in this room.";
}

interface RowsProps {
  stop: TourStop;
  plan: TourPlan;
  /** The ad's own photo here when this browser can read it. */
  adPhoto: string | null;
  liveScan: boolean;
  sampleSeed: string;
}

/** "On this stop": two rows under the stage that change with the stop. */
export function OnThisStop({ stop, plan, adPhoto, liveScan, sampleSeed }: RowsProps) {
  const hasPhoto = stop.photos.length > 0;
  const sample =
    hasPhoto && !adPhoto && plan.source === "fixture"
      ? photoFor({ source: "fixture", stock: "interior", seed: `${sampleSeed}-${stop.key}` })
      : null;
  const src = adPhoto ?? sample?.src ?? null;
  return (
    <section className="tour-onstop" aria-labelledby="tour-onstop-h" data-testid="on-this-stop">
      <h2 id="tour-onstop-h" className="tour-onstop-h ui-mono">
        On this stop
      </h2>
      <div className="tour-onstop-row" data-row="ad">
        <p className="tour-onstop-k ui-mono">The ad showed</p>
        <p className="tour-onstop-v" data-testid="on-stop-ad">
          {adShowedLine(stop, plan)}
        </p>
        {hasPhoto && (
          <Photo
            className="tour-adthumb"
            src={src}
            alt={sample?.alt ?? "The photo from the ad that was taken here"}
            stamp={adPhoto ? "ad" : "sample"}
          />
        )}
      </div>
      <div className="tour-onstop-row" data-row="scan">
        <p className="tour-onstop-k ui-mono">The scan shows</p>
        <p className="tour-onstop-v" data-testid="tour-seeing">
          {seeingLine(stop, plan, liveScan)}
        </p>
      </div>
    </section>
  );
}

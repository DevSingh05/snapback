// "On this stop" for the twin page: two rows under the stage that follow the photo being shown.
// Structure only; looks are in twin.css.
import { Photo } from "../ui/Photo";
import type { LandingState } from "./landing";

/** What the 3D scan shows for this photo, in one plain sentence. Never says more than the pose knows. */
export function scanShowsLine(state: LandingState): string {
  switch (state.kind) {
    case "loading":
      return "Loading the 3D view.";
    case "match":
      return "The camera stood at the marked spot and looked the way the cone points.";
    case "placed":
      return "The photo was taken in this home, but the scan has no camera angle for it.";
    case "elsewhere":
      return "The scan of the listed home does not hold this photo. It was taken in another building.";
    case "not_found":
      return "No place in the scan matches this photo.";
  }
}

interface Props {
  photoId: string;
  state: LandingState;
  /** The ad's photo; null draws the labelled stand-in. */
  src: string | null;
  sample: boolean;
}

export function TwinOnStop({ photoId, state, src, sample }: Props) {
  return (
    <section className="twin-onstop" aria-labelledby="twin-onstop-h" data-testid="on-this-stop">
      <h2 id="twin-onstop-h" className="twin-onstop-h ui-mono">
        On this stop
      </h2>
      <div className="twin-onstop-row">
        <p className="twin-onstop-k ui-mono">The ad showed</p>
        <p className="twin-onstop-v">{`Listing photo ${photoId}.`}</p>
        <Photo
          className="twin-adthumb"
          src={src}
          alt={sample ? "A sample interior, standing in for the ad's photo" : "The ad's photo"}
          stamp={sample ? "sample" : "ad"}
        />
      </div>
      <div className="twin-onstop-row">
        <p className="twin-onstop-k ui-mono">The scan shows</p>
        <p className="twin-onstop-v">{scanShowsLine(state)}</p>
      </div>
    </section>
  );
}

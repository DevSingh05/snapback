// The proof pair: the ad's photo beside the scan frame it matched, with numbered bone pins at
// the same spots on both and one plain caption. No lines are drawn between the photos.
// Each photo carries its stamp. The stamp sits over a corner the pins leave free; when no corner
// is free, and always at phone width, it sits under the photo, so it never covers a pin.
import "../ui/ui.css";
import "./case.css";
import { Photo, PhotoPin, STAMP_TEXT } from "../ui";
import type { ProofData, ProofShot } from "./model";

type StampAt = "bottom" | "top" | "below";

interface Spot {
  x: number;
  y: number;
}

// The stamp is at most this much of the photo, measured from its left corner (percent).
const STAMP_REACH_X = 72;
const STAMP_REACH_Y = 22;

/** Where the stamp can sit without touching a pin. */
export function stampPlace(spots: Spot[]): StampAt {
  const left = spots.filter((s) => s.x < STAMP_REACH_X);
  if (!left.some((s) => s.y > 100 - STAMP_REACH_Y)) return "bottom";
  if (!left.some((s) => s.y < STAMP_REACH_Y)) return "top";
  return "below";
}

function Shot({ shot, spots, handoff }: { shot: ProofShot; spots: Spot[]; handoff?: boolean }) {
  // With no picture the drawn stand-in shows, and the stamp must say so.
  const kind = shot.src ? shot.stamp : "drawn";
  return (
    <figure
      className={handoff ? "case-shot case-shot-handoff" : "case-shot"}
      data-stamp-at={stampPlace(spots)}
    >
      <Photo src={shot.src} alt={shot.alt} stamp={null} eager className="case-shot-photo">
        {spots.map((s, i) => (
          <PhotoPin key={i} n={i + 1} x={s.x} y={s.y} />
        ))}
      </Photo>
      <figcaption className="ui-stamp case-stamp" data-testid="case-stamp">
        {STAMP_TEXT[kind]}
      </figcaption>
    </figure>
  );
}

// `handoff` names the ad photo for the photo hand-off into the walk page (view transition
// "ad-photo"). Only one element on a page may carry the name, so only the case page's own pair
// sets it; pairs inline in the Home thread and in the story leave it off.
export function ProofPair({
  ad,
  scan,
  pins,
  kicker,
  caption,
  handoff = false,
}: ProofData & { handoff?: boolean }) {
  return (
    <div className="case-proof" data-testid="case-proof">
      <div className="case-proof-pair">
        <Shot shot={ad} spots={pins.map((p) => ({ x: p.ax, y: p.ay }))} handoff={handoff} />
        <Shot shot={scan} spots={pins.map((p) => ({ x: p.sx, y: p.sy }))} />
      </div>
      <p className="case-proof-caption">
        {kicker ? <span className="ui-mono">{kicker}</span> : null}
        <span>{caption}</span>
      </p>
    </div>
  );
}

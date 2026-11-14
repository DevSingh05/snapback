import { SourceChip } from "../components/SourceChip";
import type { DataSource } from "../contracts";
import { Parts } from "../draw/Parts";
import { NAMED_SCENE, PICTURED_SCENE } from "./aerialScenes";
import "./walk.css";

export interface AerialPane {
  /** A Vexcel tile from our own server. None: a team-made stand-in is drawn. */
  src?: string | null;
  capturedOn?: string | null;
}

interface Props {
  named: AerialPane; // the home the ad names
  pictured: AerialPane; // the home in its photos
  source: DataSource;
  /** The card's own line about the pictured home's office (written by code, lane A). */
  officeLine: string;
  /** The office name from CoStar's record. Never an address. */
  officeName?: string | null;
}

export const NAMED_LABEL = "The home the ad names";
export const PICTURED_LABEL = "The home in its photos";
export const MISMATCH_TITLE = "The ad's photos were taken in a different building.";

function StandIn({ which }: { which: "named" | "pictured" }) {
  return (
    <svg className="ma-standin" viewBox="0 0 400 300" aria-hidden="true" focusable="false">
      <Parts parts={which === "named" ? NAMED_SCENE : PICTURED_SCENE} />
    </svg>
  );
}

function Pane({
  which,
  label,
  pane,
}: {
  which: "named" | "pictured";
  label: string;
  pane: AerialPane;
}) {
  return (
    <figure className={`ma-pane ma-${which}`} data-testid={`aerial-${which}`}>
      <figcaption className="ma-label">{label}</figcaption>
      <div className="ma-tile">
        {pane.src ? (
          <img className="ma-img" src={pane.src} alt={`Aerial view: ${label.toLowerCase()}`} />
        ) : (
          <>
            <StandIn which={which} />
            <span className="rs-standin mono">Drawn stand-in (fixture)</span>
          </>
        )}
      </div>
      <p className="ma-date mono" data-testid={`aerial-${which}-caption`}>
        {pane.src
          ? pane.capturedOn
            ? `Vexcel aerial, captured ${pane.capturedOn}`
            : "Vexcel aerial"
          : "Drawn stand-in, not an aerial photo"}
      </p>
    </figure>
  );
}

// The two aerials side by side: the home the ad names, and the home its photos were taken in.
// Said in ink, with a mark and words. No address is shown, only the aerials and the office name.
export function MismatchAerials({ named, pictured, source, officeLine, officeName }: Props) {
  return (
    <section className="ma" data-testid="mismatch-aerials" aria-label="Two different buildings">
      <header className="ma-head">
        <h2 className="ma-title">{MISMATCH_TITLE}</h2>
        <SourceChip source={source} />
      </header>
      <div className="ma-pair">
        <Pane which="named" label={NAMED_LABEL} pane={named} />
        <span className="ma-versus" aria-hidden="true">
          <span className="ma-versus-line" />
        </span>
        <Pane which="pictured" label={PICTURED_LABEL} pane={pictured} />
      </div>
      <div className="ma-office" data-testid="office-line">
        <p className="ma-office-line">{officeLine}</p>
        {officeName && (
          <p className="ma-office-name">
            <span className="ma-office-key mono">Office on CoStar's record</span>
            <strong>{officeName}</strong>
          </p>
        )}
      </div>
    </section>
  );
}

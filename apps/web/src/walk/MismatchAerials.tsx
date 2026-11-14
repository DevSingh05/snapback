import { SourceChip } from "../components/SourceChip";
import type { DataSource } from "../contracts";
import { boxFaces, points, type Box, type Origin } from "./iso";
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

const O: Origin = { ox: 200, oy: 70 };

const BLOCKS: Record<"named" | "pictured", { lot: Box; home: Box[]; around: Box[] }> = {
  named: {
    lot: { x: 70, y: 70, w: 100, d: 100, h: 0 },
    home: [
      { x: 86, y: 90, w: 68, d: 58, h: 30, tone: "white" },
      { x: 86, y: 90, z: 30, w: 68, d: 58, h: 6, tone: "slate" },
    ],
    around: [
      { x: 0, y: 0, w: 52, d: 44, h: 24, tone: "pale" },
      { x: 150, y: -6, w: 56, d: 44, h: 22, tone: "pale" },
      { x: -10, y: 150, w: 50, d: 54, h: 22, tone: "pale" },
      { x: 196, y: 150, w: 44, d: 60, h: 26, tone: "pale" },
    ],
  },
  pictured: {
    lot: { x: 60, y: 60, w: 120, d: 120, h: 0 },
    home: [
      { x: 76, y: 76, w: 88, d: 88, h: 84, tone: "white" },
      { x: 76, y: 76, z: 84, w: 88, d: 88, h: 5, tone: "slate" },
    ],
    around: [
      { x: -6, y: 0, w: 50, d: 50, h: 40, tone: "pale" },
      { x: 170, y: -10, w: 50, d: 44, h: 52, tone: "pale" },
      { x: 200, y: 170, w: 40, d: 50, h: 30, tone: "pale" },
    ],
  },
};

function StandIn({ which }: { which: "named" | "pictured" }) {
  const b = BLOCKS[which];
  const { x, y, w, d } = b.lot;
  const draw = (box: Box, i: number, cls: string) => {
    const f = boxFaces(box, O);
    return (
      <g key={`${cls}-${i}`} className={`rs-box rs-${box.tone ?? "pale"} ${cls}`}>
        <polygon className="rs-face-left" points={f.left} />
        <polygon className="rs-face-right" points={f.right} />
        <polygon className="rs-face-top" points={f.top} />
      </g>
    );
  };
  return (
    <svg className="ma-standin" viewBox="0 0 400 300" aria-hidden="true" focusable="false">
      <polygon
        className="ma-ground"
        points={points(O, [-40, -40, 0], [260, -40, 0], [260, 260, 0], [-40, 260, 0])}
      />
      <polygon
        className="ma-road"
        points={points(O, [-40, 108, 0], [60, 108, 0], [60, 132, 0], [-40, 132, 0])}
      />
      <polygon
        className="ma-road"
        points={points(O, [108, 180, 0], [132, 180, 0], [132, 260, 0], [108, 260, 0])}
      />
      {b.around.filter((a) => a.x + a.y < 200).map((a, i) => draw(a, i, "ma-far"))}
      <polygon
        className="ma-lot"
        points={points(O, [x, y, 0], [x + w, y, 0], [x + w, y + d, 0], [x, y + d, 0])}
      />
      {b.home.map((h, i) => draw(h, i, "ma-home"))}
      {b.around.filter((a) => a.x + a.y >= 200).map((a, i) => draw(a, i, "ma-near"))}
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
      <p className="ma-date mono">
        {pane.capturedOn ? `Vexcel aerial, captured ${pane.capturedOn}` : "Vexcel aerial"}
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

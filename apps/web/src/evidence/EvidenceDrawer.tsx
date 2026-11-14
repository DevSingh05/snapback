import { useEffect, useRef, useState, type CSSProperties } from "react";

import { SourceChip } from "../components/SourceChip";
import { BarGauges, PointsMeter } from "./BarGauges";
import { ConfidenceChip } from "./ConfidenceChip";
import "./evidence.css";
import { drawMs, pickSpots, useCountUp } from "./match";
import { MatchSpots } from "./MatchSpots";
import { SearchSteps } from "./PickCard";
import { CHIP_LABEL, chipState, placeLine } from "./read";
import type { Calibration, EvidenceFile, EvidencePhoto } from "./types";
import { ViewToggle, type ViewChoice } from "./ViewToggle";

export const RENDER_NOTE = "Photos: renders made from the scan";
export const LABEL_NOTE = "Matterport's label, can be wrong";

interface Props {
  file: EvidenceFile;
  /** The photo to open on. Falls back to the first photo. */
  alias?: string | null;
  onClose: () => void;
  reduced: boolean;
  stacked?: boolean;
  /** Image URLs from our own server, keyed by photo alias (E3). None: stand-ins are drawn. */
  images?: Record<string, { ad?: string | null; scan?: string | null }>;
  calibration?: Calibration | null;
}

interface TableProps {
  photo: EvidencePhoto;
  bars: Record<string, number>;
  adSrc?: string | null;
  scanSrc?: string | null;
  reduced: boolean;
  stacked: boolean;
}

// The match on one dark table: the two pictures with their numbered spots, and under them the
// meter whose count rises as the spots are circled. Remounted per photo, so the draw-in replays.
function MatchTable(props: TableProps) {
  const [run, setRun] = useState(0);
  return <MatchRun key={run} {...props} onReplay={() => setRun((r) => r + 1)} />;
}

function MatchRun({
  photo,
  bars,
  adSrc,
  scanSrc,
  reduced,
  stacked,
  onReplay,
}: TableProps & { onReplay: () => void }) {
  const ms = drawMs(pickSpots(photo.points?.sampled ?? []).length);
  const count = useCountUp(photo.inliers ?? 0, ms, reduced);
  return (
    <div
      className="mt"
      data-testid="match-table"
      data-motion={reduced ? "reduced" : "full"}
      style={{ "--draw-ms": `${ms}ms` } as CSSProperties}
    >
      <MatchSpots
        photo={photo}
        adSrc={adSrc}
        scanSrc={scanSrc}
        reduced={reduced}
        stacked={stacked}
        onReplay={onReplay}
      />
      <PointsMeter photo={photo} bars={bars} count={count} />
    </div>
  );
}

// "How we know": slides over the scan. One photo at a time: the ad photo and the scan view with
// their matched spots, the three gauges, the room label and the chip.
export function EvidenceDrawer({
  file,
  alias,
  onClose,
  reduced,
  stacked = false,
  images,
  calibration,
}: Props) {
  const first = file.photos.find((p) => p.alias === alias)?.alias ?? file.photos[0]?.alias;
  const [open, setOpen] = useState(first);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const photo = file.photos.find((p) => p.alias === open);
  // Real images lead whenever our server gave them; the drawing is the labelled fallback.
  const [view, setView] = useState<ViewChoice>("real");
  const real = photo ? images?.[photo.alias] : undefined;
  const hasReal = Boolean(real?.ad && real?.scan);
  const showReal = hasReal && view === "real";

  return (
    <section
      className="ev"
      data-testid="evidence-drawer"
      data-motion={reduced ? "reduced" : "full"}
      aria-label="How we know"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <header className="ev-head">
        <h2 className="ev-title" tabIndex={-1} ref={heading}>
          How we know
        </h2>
        <SourceChip source={file.source} />
        <p className="ev-render" data-testid="render-note">
          {RENDER_NOTE}
        </p>
        <button type="button" className="ev-close" onClick={onClose}>
          Close
        </button>
      </header>
      {photo ? (
        <>
          <div className="ev-tabs" role="tablist" aria-label="The ad's photos">
            {file.photos.map((p) => {
              const state = chipState(p, file.bars);
              return (
                <button
                  key={p.alias}
                  type="button"
                  role="tab"
                  className="ev-tab"
                  aria-selected={p.alias === open}
                  data-state={state}
                  onClick={() => setOpen(p.alias)}
                >
                  <span className="mono">{p.alias}</span>
                  <span className="ev-tab-state">{CHIP_LABEL[state]}</span>
                </button>
              );
            })}
          </div>
          <div className="ev-body" role="tabpanel" aria-label={`Photo ${photo.alias}`}>
            <div className="ev-view">
              <ViewToggle
                value={showReal ? "real" : "drawing"}
                onChange={setView}
                hasReal={hasReal}
                label="Real images or the drawing"
              />
              <p className="ev-view-note" data-testid="view-note">
                {showReal
                  ? "The ad's own photo beside the view of the scan it matched."
                  : hasReal
                    ? "Drawn stand-in. Switch to Real for the ad's photo and the scan view."
                    : "Drawn stand-in: no real image is here for this photo."}
              </p>
            </div>
            <MatchTable
              key={`${photo.alias}-${stacked ? "s" : "w"}-${showReal ? "r" : "d"}`}
              photo={photo}
              bars={file.bars}
              adSrc={showReal ? real?.ad : null}
              scanSrc={showReal ? real?.scan : null}
              reduced={reduced}
              stacked={stacked}
            />
            <div className="ev-side">
              <div className="ev-result">
                <h3 className="ev-place" data-testid="place-line">
                  {placeLine(photo)}
                </h3>
                <ConfidenceChip photo={photo} bars={file.bars} calibration={calibration} />
                {photo.room_label && <p className="ev-note">{LABEL_NOTE}</p>}
                {photo.status === "located_elsewhere" && (
                  <p className="ev-note">
                    Held to the stricter bar for a photo placed outside the home the ad names.
                  </p>
                )}
              </div>
              <BarGauges
                key={photo.alias}
                photo={photo}
                bars={file.bars}
                thresholdsVersion={file.thresholds_version}
                adSrc={showReal ? real?.ad : null}
                withPoints={false}
              />
              <SearchSteps searches={photo.searches} />
            </div>
          </div>
        </>
      ) : (
        <p className="ev-empty" data-testid="evidence-empty">
          No photo has been measured yet.
        </p>
      )}
    </section>
  );
}

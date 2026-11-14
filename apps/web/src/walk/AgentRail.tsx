import { useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { DataSource, TraceEvent } from "../contracts";
import { FilesTree } from "../evidence/FilesTree";
import { pickOutcome } from "../evidence/match";
import { MatchSpots } from "../evidence/MatchSpots";
import { PickCard } from "../evidence/PickCard";
import { barsFor, findPhoto } from "../evidence/read";
import type { EvidenceFile } from "../evidence/types";
import {
  KIND_TAG,
  lanes,
  lastLine,
  railFiles,
  railItems,
  summaryLine,
  type RailItem,
} from "./rail";
import "./walk.css";

interface Props {
  /** Parsed trace events only (trace/parse.ts). The rail draws nothing else. */
  events: TraceEvent[];
  source: DataSource;
  /** The evidence file, so a step that names a photo can show its matched points. */
  evidence?: EvidenceFile | null;
  reduced: boolean;
  /** Opens "How we know" on a photo. */
  onOpenPhoto?: (alias: string) => void;
}

function Proof({
  item,
  evidence,
  onOpenPhoto,
}: {
  item: RailItem;
  evidence: EvidenceFile;
  onOpenPhoto?: (alias: string) => void;
}) {
  const photo = item.alias ? findPhoto(evidence, item.alias) : undefined;
  if (!photo || !photo.points) return null;
  const bar = barsFor(photo, evidence.bars).inliers;
  const body = (
    <>
      <MatchSpots photo={photo} reduced mini />
      <span className="ar-proof-text mono">
        {photo.alias}: {photo.points.n_total} matching points
        {bar != null ? `, ${bar} needed` : ""}
      </span>
    </>
  );
  return onOpenPhoto ? (
    <button
      type="button"
      className="ar-proof"
      data-testid="rail-proof"
      onClick={() => onOpenPhoto(photo.alias)}
      aria-label={`How we know: photo ${photo.alias}`}
    >
      {body}
    </button>
  ) : (
    <div className="ar-proof" data-testid="rail-proof">
      {body}
    </div>
  );
}

function Line({
  item,
  evidence,
  onOpenPhoto,
}: { item: RailItem } & Omit<Props, "events" | "source" | "reduced">) {
  const e = item.event;
  const kind: string = e.kind;
  const isPick = kind === "choice";
  return (
    <li
      className={`ar-line ar-${kind}`}
      data-testid="rail-line"
      data-kind={kind}
      data-seq={e.seq}
      data-agent={item.agent}
    >
      <span className="ar-tag mono">{KIND_TAG[kind] ?? kind}</span>
      <div className="ar-body">
        {kind === "agent" && e.pick && (
          <p className="ar-handoff">
            <span className="ar-handoff-arrow" aria-hidden="true" />
            <span className="sr-only">Handed to </span>
            <strong className="ar-agent-name">{e.pick}</strong>
          </p>
        )}
        {kind === "file" && e.pick && (
          <p className="ar-file">
            <span className="mono ar-file-path">{e.pick}</span>
            <span
              className={`ft-badge ft-badge-${e.chosen_by === "model" ? "agent" : "code"}`}
              data-testid="rail-written-by"
            >
              {e.chosen_by === "model" ? "written by the agent" : "written by code"}
            </span>
          </p>
        )}
        {kind === "tool" && e.pick && <p className="ar-tool mono">{e.pick}</p>}
        {isPick && (
          <PickCard
            options={e.options}
            pick={e.pick ?? null}
            by={e.choice === "which_spot" ? "random" : e.chosen_by}
            why={e.reason}
            result={
              evidence && item.alias ? pickOutcome(findPhoto(evidence, item.alias), e.pick) : null
            }
          />
        )}
        {!isPick && e.reason && <p className="ar-reason">{e.reason}</p>}
        {evidence && (isPick || kind === "unsure") && (
          <Proof item={item} evidence={evidence} onOpenPhoto={onOpenPhoto} />
        )}
      </div>
    </li>
  );
}

// The agent at work, as a relay: who holds the case, what each one measured, wrote and picked.
// It leads with the measured thing (the matched points), never a to-do list, and it draws only
// what the trace stream delivered.
export function AgentRail({ events, source, evidence = null, reduced, onOpenPhoto }: Props) {
  const [open, setOpen] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const items = railItems(events);
  const who = lanes(items);
  const holder = items.at(-1)?.agent;
  const files = railFiles(events);
  const last = items.at(-1)?.event;

  return (
    <aside
      className="ar"
      data-testid="agent-rail"
      data-open={open ? "true" : "false"}
      data-motion={reduced ? "reduced" : "full"}
      aria-label="The agents on this case"
    >
      <header className="ar-head">
        <h2 className="ar-title">On the case</h2>
        <SourceChip source={source} />
        <p className="ar-count mono" data-testid="rail-summary">
          {summaryLine(events)}
        </p>
        <button
          type="button"
          className="ar-sheet"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="ar-sheet-last">{last ? lastLine(last) : "No steps yet"}</span>
          <span className="ar-sheet-count mono">{summaryLine(events)}</span>
        </button>
      </header>
      <div className="ar-fold">
        {items.length === 0 ? (
          <p className="ar-empty" data-testid="rail-empty">
            No steps yet. Each one appears here as the agents work.
          </p>
        ) : (
          <>
            <ol className="ar-relay" aria-label="Who has held the case">
              {who.map((name) => (
                <li
                  key={name}
                  className="ar-runner"
                  data-testid="rail-agent"
                  aria-current={name === holder ? "true" : undefined}
                >
                  {name}
                </li>
              ))}
            </ol>
            <ol className="ar-list" aria-live="polite">
              {items.map((item) => (
                <Line
                  key={item.event.seq}
                  item={item}
                  evidence={evidence}
                  onOpenPhoto={onOpenPhoto}
                />
              ))}
            </ol>
            <p className="ar-rule">The agents pick what to check next. Code sets every number.</p>
            <div className="ar-files">
              <button
                type="button"
                className="ar-files-toggle"
                aria-expanded={showFiles}
                onClick={() => setShowFiles((s) => !s)}
              >
                Files ({files.length})
              </button>
              {showFiles && <FilesTree files={files} />}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

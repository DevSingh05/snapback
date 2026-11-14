import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { DataSource, TourStop, TraceEvent } from "../contracts";
import { FilesTree } from "../evidence/FilesTree";
import { pickOutcome } from "../evidence/match";
import { MatchLines } from "../evidence/MatchLines";
import { PickCard } from "../evidence/PickCard";
import { barsFor, findPhoto } from "../evidence/read";
import type { EvidenceFile, EvidencePhoto } from "../evidence/types";
import {
  KIND_TAG,
  lanes,
  plainLine,
  railFiles,
  railItems,
  stepForStop,
  stopLine,
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
  /** The walk stop on screen. With it the rail follows the walk: the step behind this stop is
   *  lit and open, every other step is one line. Without it every step is open, as a plain log. */
  stop?: TourStop | null;
  /** The evidence row of the ad photo placed at this stop (walkLook photoAt), if any. */
  photo?: EvidencePhoto | null;
}

/** How long a scroll inside the rail holds off the follow, in ms. */
export const FOLLOW_PAUSE_MS = 8000;
const GLIDE_MS = 420;
const GLIDE_EASE = "cubic-bezier(0.16, 1, 0.3, 1)";

function Proof({
  alias,
  evidence,
  onOpenPhoto,
}: {
  alias: string | null;
  evidence: EvidenceFile;
  onOpenPhoto?: (alias: string) => void;
}) {
  const photo = alias ? findPhoto(evidence, alias) : undefined;
  if (!photo || !photo.points) return null;
  const bar = barsFor(photo, evidence.bars).inliers;
  const body = (
    <>
      <MatchLines photo={photo} reduced mini />
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

interface LineProps {
  item: RailItem;
  /** The step's place in the run, from 1. */
  n: number;
  evidence: EvidenceFile | null;
  onOpenPhoto?: (alias: string) => void;
  /** True when the rail follows the walk, so steps fold to one line. */
  folds: boolean;
  open: boolean;
  lit: boolean;
  /** What this step means at the stop on screen; set on the lit step only. */
  here: string | null;
  /** The ad photo placed at the stop on screen, shown on the lit step. */
  hereAlias: string | null;
  onToggle: () => void;
}

function Line({
  item,
  n,
  evidence,
  onOpenPhoto,
  folds,
  open,
  lit,
  here,
  hereAlias,
  onToggle,
}: LineProps) {
  const e = item.event;
  const kind: string = e.kind;
  const isPick = kind === "choice";
  const tag = KIND_TAG[kind] ?? kind;
  const ownProof = Boolean(evidence && (isPick || kind === "unsure") && item.alias);
  const num = String(n).padStart(2, "0");
  return (
    <li
      className={`ar-line ar-${kind}`}
      data-testid="rail-line"
      data-kind={kind}
      data-seq={e.seq}
      data-agent={item.agent}
      data-flip={e.seq}
      data-state={open ? "open" : "closed"}
      data-lit={lit ? "true" : undefined}
      aria-current={lit ? "step" : undefined}
    >
      {folds && !lit ? (
        <button
          type="button"
          className="ar-row"
          aria-expanded={open}
          aria-label={`Step ${n}: ${plainLine(e)}`}
          onClick={onToggle}
        >
          <span className="ar-n mono">{num}</span>
          <span className="ar-row-text">{open ? tag : plainLine(e)}</span>
        </button>
      ) : (
        <span className="ar-tag mono">
          {folds && <span className="ar-n">{num}</span>}
          {tag}
        </span>
      )}
      {open && (
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
          {here && (
            <p className="ar-here" data-testid="rail-here">
              <span className="ar-here-tag mono">At this stop</span>
              {here}
            </p>
          )}
          {evidence && ownProof && (
            <Proof alias={item.alias} evidence={evidence} onOpenPhoto={onOpenPhoto} />
          )}
          {evidence && hereAlias && !(ownProof && item.alias === hereAlias) && (
            <Proof alias={hereAlias} evidence={evidence} onOpenPhoto={onOpenPhoto} />
          )}
        </div>
      )}
    </li>
  );
}

/** Where each gliding piece sits inside the scroll box, by its data-flip key. */
function measure(box: HTMLElement): Map<string, number> {
  const at = new Map<string, number>();
  for (const el of box.querySelectorAll<HTMLElement>("[data-flip]"))
    at.set(el.dataset.flip!, el.offsetTop);
  return at;
}

// How the check was done, as a relay: who held the case, what each one measured, wrote and
// picked. It draws only what the trace stream delivered. Given the walk stop on screen it follows
// the walk: the step behind that stop is lit and open, and the list glides it into view.
export function AgentRail({
  events,
  source,
  evidence = null,
  reduced,
  onOpenPhoto,
  stop = null,
  photo = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const [paused, setPaused] = useState(false);
  const items = railItems(events);
  const who = lanes(items);
  const files = railFiles(events);
  const folds = Boolean(stop);
  const lit = stop ? stepForStop(items, stop, photo) : null;
  const litAt = items.findIndex((i) => i.event.seq === lit);
  const litItem = litAt >= 0 ? items[litAt]! : null;
  const holder = (litItem ?? items.at(-1))?.agent;
  const shown = litItem ?? items.at(-1) ?? null;
  const line = stop ? stopLine(stop, photo, evidence?.bars ?? {}) : null;
  // Never the same sentence twice: the step's own reason may already say it.
  const here =
    line && litItem && !litItem.event.reason.toLowerCase().includes(line.toLowerCase().slice(0, -1))
      ? line
      : null;
  const hereAlias = stop && stop.photos.length > 0 ? (photo?.alias ?? null) : null;

  // The reader's own scroll wins: it holds the follow off for a while, or until they ask.
  const timer = useRef<number | undefined>(undefined);
  const hold = () => {
    if (!folds) return;
    window.clearTimeout(timer.current);
    setPaused(true);
    timer.current = window.setTimeout(() => setPaused(false), FOLLOW_PAUSE_MS);
  };
  const follow = () => {
    window.clearTimeout(timer.current);
    setPaused(false);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Follow the walk. When the lit step changes, the list is laid out afresh (one step opens, one
  // folds) and scrolled so the lit step sits just under the top with the step before it in view;
  // then every row glides from where it was to where it is now, as one move. Under reduced motion
  // the rows are simply in their new place.
  const box = useRef<HTMLDivElement>(null);
  const tops = useRef(new Map<string, number>());
  const last = useRef<{ lit: number | null; paused: boolean; open: boolean }>({
    lit: null,
    paused: false,
    open: false,
  });
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const before = tops.current;
    const was = last.current;
    last.current = { lit, paused, open };
    const scrolledBefore = el.scrollTop;
    const now = measure(el);
    tops.current = now;
    if (lit == null) return;
    const moved = was.lit !== lit;
    if (!moved && was.paused === paused && was.open === open) return;
    if (!paused) {
      const row = el.querySelector<HTMLElement>(`[data-seq="${lit}"]`);
      const lead = row?.previousElementSibling as HTMLElement | null;
      if (row) el.scrollTop = Math.max(0, (lead ?? row).offsetTop - 8);
    }
    if (reduced || was.lit == null) return;
    const shift = el.scrollTop - scrolledBefore;
    for (const piece of el.querySelectorAll<HTMLElement>("[data-flip]")) {
      const from = before.get(piece.dataset.flip!);
      if (from == null || typeof piece.animate !== "function") continue;
      const dy = from - now.get(piece.dataset.flip!)! + shift;
      if (Math.abs(dy) >= 1)
        piece.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
          duration: GLIDE_MS,
          easing: GLIDE_EASE,
        });
    }
  });

  const toggle = (seq: number) =>
    setOpened((s) => {
      const next = new Set(s);
      if (!next.delete(seq)) next.add(seq);
      return next;
    });

  return (
    <aside
      className="ar"
      data-testid="agent-rail"
      data-open={open ? "true" : "false"}
      data-follow={!folds ? undefined : paused ? "paused" : "on"}
      data-motion={reduced ? "reduced" : "full"}
      aria-label="How SNAPBACK checked this ad"
    >
      <header className="ar-head">
        <h2 className="ar-title">How SNAPBACK checked this ad</h2>
        <SourceChip source={source} />
        <p className="ar-count" data-testid="rail-summary">
          {items.length === 0
            ? "Steps appear here as our agents work."
            : `${items.length} ${items.length === 1 ? "step" : "steps"} our agents took, in order.${
                folds ? " The step behind this stop is lit." : ""
              }`}
        </p>
        <button
          type="button"
          className="ar-sheet"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="ar-sheet-label">How we checked</span>
          <span className="ar-sheet-last" data-testid="rail-now">
            {shown
              ? `Step ${items.indexOf(shown) + 1} of ${items.length}: ${plainLine(shown.event)}`
              : "No steps yet"}
          </span>
        </button>
      </header>
      <div className="ar-fold">
        {items.length === 0 ? (
          <p className="ar-empty" data-testid="rail-empty">
            No steps yet. Each one appears here as the agents work.
          </p>
        ) : (
          <>
            <ol className="ar-relay" aria-label="Who held the case, in order">
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
            <div
              className="ar-scroll"
              ref={box}
              onWheel={hold}
              onTouchMove={hold}
              onKeyDown={(e) => {
                if (/^(Arrow(Up|Down)|Page(Up|Down)|Home|End)$/.test(e.key)) hold();
              }}
            >
              <ol className="ar-list">
                {items.map((item, i) => (
                  <Line
                    key={item.event.seq}
                    item={item}
                    n={i + 1}
                    evidence={evidence}
                    onOpenPhoto={onOpenPhoto}
                    folds={folds}
                    lit={item.event.seq === lit}
                    open={!folds || item.event.seq === lit || opened.has(item.event.seq)}
                    here={item.event.seq === lit ? here : null}
                    hereAlias={item.event.seq === lit ? hereAlias : null}
                    onToggle={() => toggle(item.event.seq)}
                  />
                ))}
              </ol>
              <div className="ar-foot" data-flip="foot">
                <p className="ar-rule" data-testid="rail-counts">
                  {summaryLine(events)}. The agents pick what to check next. Code sets every number.
                </p>
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
              </div>
            </div>
            {folds && paused && (
              <button
                type="button"
                className="ar-follow"
                data-testid="rail-follow"
                onClick={follow}
              >
                Follow the walk
              </button>
            )}
          </>
        )}
      </div>
    </aside>
  );
}

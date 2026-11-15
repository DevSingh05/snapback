// The check team as a crew you can watch work. The home in the ad stands in the middle of its
// plot, drawn with the same kit as every other drawn scene in the app. The Planner leads from
// the far corner, the members stand round the home, the Decider sits at its desk in front.
//
// The loop: when a recorded step starts a member's work, the Planner tosses it a note; the
// member works (its prop moves); a bubble says what it is doing and then what it found, in the
// roster's and the card's own words; when it is done its note flies on to the Decider's desk,
// red tagged for a red flag; the Decider stamps last, once floor.verdict is there (so after
// the fresh card on a run that was watched live). Members the ad did not need sit on the bench
// at the edge; a check the plan left out shows as a dashed outline.
//
// With `moving` off (reduced motion, or nothing playing) no note flies and nothing loops: the
// states, the bubbles and the stamp still change. Nothing here works out a result.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import "../draw/draw.css";
import "./crew.css";
import { Parts } from "../draw/Parts";
import { makeScene, part, project, type Part, type Prim } from "../draw/kit";
import { deskWord } from "./AgentStrip";
import { Badge } from "./Badge";
import {
  HOME,
  ORIGIN,
  PLOT,
  VIEW,
  crewActions,
  crewBubbles,
  crewCast,
  reported,
  type CrewActor,
} from "./crew";
import { DESK_TOP, figure } from "./crewFigure";
import type { Floor, Lang, TeamView } from "./model";
import { shortName } from "./TeamGraph";
import type { RoomWords } from "./words";

interface Note {
  id: number;
  who: string;
  kind: "brief" | "report";
  flag: boolean;
  from: [number, number];
  to: [number, number];
  delay: number;
}

function Prims({ prims }: { prims: Prim[] }) {
  return <Parts parts={[{ name: "p", prims }]} />;
}

/** The plot: a slab of lawn, the walk that loops round the home, the home itself. */
function ground(): { lawn: Part[]; home: Part[] } {
  const s = makeScene(ORIGIN);
  const a = 44; // the walk's outer edge
  const t = 11; // its width
  const b = PLOT - a;
  const door = HOME.y + HOME.d * 0.5;
  return {
    lawn: [
      part("slab", [
        s.contact(0, 0, PLOT, PLOT, 12, -8),
        s.onY("house-plinth-left", PLOT, 0, PLOT, -8, 0),
        s.onX("house-plinth-right", PLOT, 0, PLOT, -8, 0),
        s.onZ("dk-lawn", 0, 0, 0, PLOT, PLOT),
      ]),
      part("walk", [
        s.onZ("dk-path", 0.05, a, a, b - a, t),
        s.onZ("dk-path", 0.05, a, b - t, b - a, t),
        s.onZ("dk-path", 0.05, a, a, t, b - a),
        s.onZ("dk-path", 0.05, b - t, a, t, b - a),
        s.onZ("dk-path", 0.05, HOME.x + HOME.w, door, b - t - HOME.x - HOME.w, 12),
      ]),
      s.tree(62, 62, 0.9),
    ],
    home: [
      ...s.house(HOME.x, HOME.y, HOME.w, HOME.d, HOME.h, "white", "slate"),
      s.shrub(HOME.x + 4, HOME.y + HOME.d + 3, 20, 5),
      s.tree(150, 150, 0.7),
    ],
  };
}

const HOME_DEPTH = HOME.x + HOME.w / 2 + HOME.y + HOME.d / 2;
const [PILE_X, PILE_Y] = project(DESK_TOP, { ox: 0, oy: 0 });
const pct = (v: number, of: number) => `${Math.round((v / of) * 10000) / 100}%`;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function Figure({
  actor,
  notes,
  onPick,
}: {
  actor: CrewActor;
  notes: { id: string; flag: boolean }[];
  onPick?: (id: string) => void;
}) {
  const fig = useMemo(() => figure(actor.persona), [actor.persona]);
  return (
    <g
      className="cs-actor"
      transform={`translate(${actor.sx} ${actor.sy}) scale(${actor.scale})`}
      data-testid="crew-actor"
      data-who={actor.id}
      data-persona={actor.persona}
      data-place={actor.place}
      data-state={actor.state}
      data-tone={actor.tone}
      onClick={onPick && actor.place !== "bench" ? () => onPick(actor.id) : undefined}
    >
      {actor.place === "bench" ? null : (
        <polygon className="cs-pad" points="0,-11 19,0 0,11 -19,0" />
      )}
      <g className="cs-figure">
        <Prims prims={fig.back} />
        <g className="cs-body">
          <Prims prims={fig.body} />
        </g>
        <Prims prims={fig.front} />
        {actor.place === "desk"
          ? notes.map((n, i) => (
              <g
                key={n.id}
                className="cs-filed"
                data-flag={n.flag ? "yes" : "no"}
                data-testid="crew-filed"
                transform={`translate(${PILE_X + (i % 2) * 1.6} ${PILE_Y - i * 1.5})`}
              >
                <polygon points="-7,0 0,-4 7,0 0,4" />
                {n.flag ? (
                  <polygon className="cs-flagged" points="2.4,-2.6 7,0 4.6,1.4 0,-1.2" />
                ) : null}
              </g>
            ))
          : null}
        <g className="cs-prop">
          <Prims prims={fig.prop} />
        </g>
        <g className="cs-fx">
          <Prims prims={fig.fx} />
        </g>
      </g>
    </g>
  );
}

export interface CrewSceneProps {
  floor: Floor;
  team: TeamView;
  w: RoomWords;
  lang?: Lang;
  // A run is playing and motion is allowed: notes may fly and props may move.
  moving: boolean;
  // The card's verdict colour for the stamp (case/model VERDICT_TONE). Never worked out here.
  verdictTone?: string;
  onPick?: (deskId: string) => void;
}

export function CrewScene({
  floor,
  team,
  w,
  lang = "en",
  moving,
  verdictTone = "slate",
  onPick,
}: CrewSceneProps) {
  const cast = useMemo(() => crewCast(floor, team), [floor, team]);
  // Far to near for drawing; the tags read in the order the members came into the run.
  const staged = cast.filter((a) => a.place !== "bench");
  const turn = new Map(team.shown.map((d, i) => [d.card.id, i]));
  const tagged = [...staged].sort((a, b) => (turn.get(a.id) ?? 0) - (turn.get(b.id) ?? 0));
  const bench = cast.filter((a) => a.place === "bench");
  const bubbles = crewBubbles(floor, cast);
  const filed = reported(floor);
  const scene = useMemo(ground, []);
  const spot = (id: string) => cast.find((a) => a.id === id);
  const lead = cast.find((a) => a.place === "lead");
  const judge = cast.find((a) => a.place === "desk");

  // Notes in the air, from recorded state changes only.
  const seen = useRef<Floor | null>(null);
  const nextId = useRef(0);
  const [notes, setNotes] = useState<Note[]>([]);
  const [stamped, setStamped] = useState(false);
  const key =
    floor.desks.map((d) => `${d.card.id}:${d.state}`).join(",") + (floor.verdict ? "|v" : "");
  useEffect(() => {
    const acts = crewActions(seen.current, floor);
    seen.current = floor;
    if (!floor.verdict) setStamped(false);
    if (!moving || acts.length === 0) return;
    const fresh: Note[] = [];
    for (const act of acts) {
      if (act.kind === "stamp") {
        setStamped(true);
        continue;
      }
      const member = spot(act.kind === "brief" ? act.to : act.from);
      if (!member || member.place !== "ring") continue;
      const hand: [number, number] = [member.sx, member.sy - 34];
      if (act.kind === "brief" && lead)
        fresh.push({
          id: nextId.current++,
          who: member.id,
          kind: "brief",
          flag: false,
          from: [lead.sx + 8, lead.sy - 34],
          to: hand,
          delay: 0,
        });
      if (act.kind === "report" && judge)
        fresh.push({
          id: nextId.current++,
          who: member.id,
          kind: "report",
          flag: act.flag,
          from: hand,
          to: [judge.sx + PILE_X, judge.sy + PILE_Y - 6],
          // A member that started and finished in one look still gets its note first.
          delay: acts.some((a) => a.kind === "brief" && a.to === act.from) ? 620 : 0,
        });
    }
    if (fresh.length > 0) setNotes((old) => [...old.slice(-5), ...fresh]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, moving]);
  useEffect(() => {
    if (!moving) setNotes([]);
  }, [moving]);

  const far = staged.filter((a) => a.depth < HOME_DEPTH);
  const near = staged.filter((a) => a.depth >= HOME_DEPTH);
  const flying = new Set(notes.filter((n) => n.kind === "report").map((n) => n.id));
  // A note still in the air has not reached the desk yet.
  const onDesk = filed.slice(0, Math.max(0, filed.length - flying.size));

  return (
    <div
      className="cs"
      data-testid="crew-scene"
      data-moving={moving ? "yes" : "no"}
      data-phase={floor.phase}
    >
      <div className="cs-stage" style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}>
        <svg
          className="cs-svg"
          viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
          aria-hidden="true"
          focusable="false"
        >
          <Parts parts={scene.lawn} />
          {far.map((a) => (
            <Figure key={a.id} actor={a} notes={onDesk} onPick={onPick} />
          ))}
          <g data-testid="crew-home" className="cs-home">
            <Parts parts={scene.home} />
          </g>
          {near.map((a) => (
            <Figure key={a.id} actor={a} notes={onDesk} onPick={onPick} />
          ))}
          {bench.map((a) => (
            <Figure key={a.id} actor={a} notes={[]} />
          ))}
          {notes.map((n) => (
            <g
              key={n.id}
              className="cs-note"
              data-testid="crew-note"
              data-kind={n.kind}
              data-agent={n.who}
              data-flag={n.flag ? "yes" : "no"}
              style={
                {
                  "--x0": `${n.from[0]}px`,
                  "--y0": `${n.from[1]}px`,
                  "--x1": `${n.to[0]}px`,
                  "--y1": `${n.to[1]}px`,
                  animationDelay: `${n.delay}ms`,
                } as CSSProperties
              }
              onAnimationEnd={(e) => {
                if (e.target === e.currentTarget)
                  setNotes((old) => old.filter((q) => q.id !== n.id));
              }}
            >
              <g className="cs-note-arc" style={{ animationDelay: `${n.delay}ms` }}>
                <rect className="cs-note-paper" x="-6.5" y="-8" width="13" height="16" />
                <path className="cs-note-lines" d="M-3.6 -3.4h7.2M-3.6 0h7.2M-3.6 3.4h4.2" />
                {n.flag ? (
                  <rect className="cs-flagged" x="2" y="-11.5" width="7" height="7" />
                ) : n.kind === "brief" ? (
                  <rect className="cs-note-clip" x="-2.6" y="-10" width="5.2" height="3.4" />
                ) : null}
              </g>
            </g>
          ))}
        </svg>

        <ol className="cs-tags" aria-label={w.team}>
          {tagged.map((a) => {
            const desk = a.desk!;
            const side = a.place === "ring" ? a.side : a.place;
            const x =
              a.place === "lead"
                ? a.sx + 62
                : a.place === "desk"
                  ? a.sx - 84
                  : clamp(a.sx + (a.side === "left" ? -14 : 14), 62, VIEW.w - 62);
            const y = a.place === "lead" ? a.sy - 52 : a.place === "desk" ? a.sy - 12 : a.sy + 9;
            const body = (
              <>
                <span className="cs-tag-name">
                  <Badge id={a.id} size={18} />
                  {shortName(a.card.name)}
                </span>
                <span className="cs-tag-model ui-mono" title={w.runsOn} data-testid="node-model">
                  {desk.model === "code" ? w.code : desk.model}
                </span>
                <span className="cs-tag-state ui-mono" data-testid="node-state">
                  {deskWord(desk, lang)}
                </span>
              </>
            );
            return (
              <li
                key={a.id}
                className="cs-tag"
                style={{ left: pct(x, VIEW.w), top: pct(y, VIEW.h) }}
                data-side={side}
                data-who={a.id}
                data-agent={a.id}
                data-state={a.state}
                data-tone={a.tone}
                data-testid="team-node"
              >
                {onPick ? (
                  <button type="button" onClick={() => onPick(a.id)}>
                    {body}
                  </button>
                ) : (
                  <span className="cs-tag-in">{body}</span>
                )}
              </li>
            );
          })}
        </ol>

        {/* The same words are in the thread below, which is the part a screen reader hears. */}
        <div className="cs-bubbles" aria-hidden="true">
          {[...bubbles].reverse().map((b) => {
            const a = spot(b.deskId)!;
            const top = a.sy - 62 * a.scale;
            const style: CSSProperties =
              a.place === "lead"
                ? { right: pct(VIEW.w - a.sx + 20, VIEW.w), top: pct(6, VIEW.h) }
                : a.side === "right"
                  ? {
                      right: pct(clamp(VIEW.w - a.sx - 16, 2, VIEW.w), VIEW.w),
                      bottom: pct(VIEW.h - top, VIEW.h),
                    }
                  : {
                      left: pct(clamp(a.sx - 16, 2, VIEW.w), VIEW.w),
                      bottom: pct(VIEW.h - top, VIEW.h),
                    };
            const desk = a.desk!;
            return (
              <p
                key={`${b.deskId}-${b.kind}`}
                className="cs-bubble"
                style={style}
                data-testid="crew-bubble"
                data-agent={b.deskId}
                data-who={b.deskId}
                data-kind={b.kind}
                data-tone={b.tone}
                data-side={a.place === "lead" ? "lead" : a.side === "right" ? "right" : "left"}
              >
                <Badge id={b.deskId} size={20} />
                <span className="cs-bubble-text">
                  <span className="cs-bubble-who ui-mono">
                    {shortName(a.card.name)}
                    {b.kind === "finding" ? ` · ${deskWord(desk, lang)}` : ""}
                  </span>
                  {b.text}
                  {b.kind === "working" ? "…" : ""}
                </span>
              </p>
            );
          })}
        </div>

        {floor.verdict && judge ? (
          <p
            className="cs-verdict"
            style={{ left: pct(judge.sx + 34, VIEW.w), top: pct(judge.sy - 30, VIEW.h) }}
            data-testid="crew-verdict"
            data-verdict={verdictTone}
            data-stamped={stamped ? "yes" : "no"}
            aria-hidden="true"
          >
            {floor.verdict.headline}
          </p>
        ) : null}

        {bench.length > 0 ? (
          <p
            className="cs-bench"
            style={{ top: pct(VIEW.h - 40, VIEW.h) }}
            data-testid="team-not-needed"
          >
            <span className="ui-mono">{w.notNeeded}: </span>
            {bench.map((a) => a.card.name).join(", ")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

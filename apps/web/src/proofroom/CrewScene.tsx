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
// The setting (crewGround.ts) is there so the crew sits well beside the listing's real photos:
// a sky with a low warm sun, a street of neighbours fading into haze, a lawn with stripes and
// a paved path, and a soft shadow under the home and under every member. What a member says
// sits in one of two slots over the sky, large enough to read from across a room, and the
// member who is speaking carries a small speech mark.
//
// With `moving` off (reduced motion, or nothing playing) no note flies and nothing loops: the
// states, the bubbles and the stamp still change. Nothing here works out a result.
import { memo, useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react";

import "../draw/draw.css";
import "./crew.css";
import { Parts } from "../draw/Parts";
import { project, type Prim } from "../draw/kit";
import { deskWord } from "./AgentStrip";
import { Badge } from "./Badge";
import {
  BUBBLES_MAX,
  HOME,
  VIEW,
  bubbleSlots,
  crewActions,
  crewBubbles,
  crewCast,
  reported,
  type CrewActor,
} from "./crew";
import { DESK_TOP, figure } from "./crewFigure";
import { crewScenery } from "./crewGround";
import { BENCH_LINE, SLOTS, STAMP, nameLines, tagLayout, type Box } from "./crewLayout";
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

// Where the far ground meets the sky, and how far down the haze reaches, in stage units.
const HORIZON = 150;
const HAZE_END = 300;
// A far line of trees along the horizon: a fixed silhouette, low and uneven.
const RIDGE = (() => {
  const rise = [6, 11, 8, 14, 9, 5, 12, 16, 10, 7, 13, 9, 6, 11, 15, 8, 5, 10, 13, 7, 9];
  const step = VIEW.w / (rise.length - 1);
  const top = rise.map((r, i) => `${(i * step).toFixed(1)} ${HORIZON - r}`).join(" L");
  return `M0 ${HORIZON + 2} L${top} L${VIEW.w} ${HORIZON + 2} Z`;
})();

const HOME_DEPTH = HOME.x + HOME.w / 2 + HOME.y + HOME.d / 2;
const [PILE_X, PILE_Y] = project(DESK_TOP, { ox: 0, oy: 0 });
const pct = (v: number, of: number) => `${Math.round((v / of) * 10000) / 100}%`;
/** A box of crewLayout.ts as CSS, in parts of the stage. */
const place = (b: Box): CSSProperties => ({
  left: pct(b.x, VIEW.w),
  top: pct(b.y, VIEW.h),
  width: pct(b.w, VIEW.w),
  height: pct(b.h, VIEW.h),
});

interface GradIds {
  sky: string;
  sun: string;
  haze: string;
  shade: string;
}

/** Everything that never changes while a run plays: the sky, the streets, the neighbours, the
 *  lawn. Drawn once; the player's clock does not redraw it. */
const Setting = memo(function Setting({ ids }: { ids: GradIds }) {
  const scene = useMemo(crewScenery, []);
  return (
    <>
      <defs>
        <linearGradient id={ids.sky} x1="0" y1="0" x2="0" y2="1">
          <stop className="cs-sky-high" offset="0" />
          <stop className="cs-sky-low" offset="1" />
        </linearGradient>
        <radialGradient id={ids.sun} cx="0.1" cy="0.5" r="0.75">
          <stop className="cs-sun-stop" offset="0" stopOpacity="0.85" />
          <stop className="cs-sun-stop" offset="1" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={ids.haze} x1="0" y1="0" x2="0" y2="1">
          <stop className="cs-haze-stop" offset="0" stopOpacity="0" />
          <stop className="cs-haze-stop" offset="0.5" stopOpacity="0.92" />
          <stop className="cs-haze-stop" offset="1" stopOpacity="0" />
        </linearGradient>
        <radialGradient id={ids.shade}>
          <stop className="cs-shade-stop" offset="0.2" stopOpacity="0.42" />
          <stop className="cs-shade-stop" offset="1" stopOpacity="0" />
        </radialGradient>
      </defs>
      <g data-testid="crew-sky" className="cs-sky">
        <rect width={VIEW.w} height={HORIZON + 4} fill={`url(#${ids.sky})`} />
        <rect width={VIEW.w} height={HORIZON + 4} fill={`url(#${ids.sun})`} />
        <path className="cs-ridge" d={RIDGE} />
        <rect className="cs-verge" y={HORIZON} width={VIEW.w} height={VIEW.h - HORIZON} />
      </g>
      <Parts parts={scene.streets} />
      <g data-testid="crew-backdrop" className="cs-backdrop">
        <Parts parts={scene.backdrop} />
      </g>
      <rect
        data-testid="crew-haze"
        className="cs-haze"
        width={VIEW.w}
        height={HAZE_END}
        fill={`url(#${ids.haze})`}
      />
      <Parts parts={scene.verge} />
      <Parts parts={scene.lawn} />
      <g data-testid="crew-home-shadow" className="cs-soft">
        <Prims prims={[scene.shadow]} />
      </g>
    </>
  );
});

/** The home in the ad: it never changes either. */
const Home = memo(function Home() {
  const scene = useMemo(crewScenery, []);
  return (
    <g data-testid="crew-home" className="cs-home">
      <Parts parts={scene.home} />
    </g>
  );
});

function Figure({
  actor,
  notes,
  shade,
  speaking = false,
  onPick,
}: {
  actor: CrewActor;
  notes: { id: string; flag: boolean }[];
  // The id of the soft shadow's gradient.
  shade: string;
  speaking?: boolean;
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
      data-speaking={speaking ? "yes" : "no"}
      onClick={onPick && actor.place !== "bench" ? () => onPick(actor.id) : undefined}
    >
      {/* A soft shadow on the grass, cast the way the home's is. */}
      <ellipse className="cs-shadow" cx="5" cy="3" rx="21" ry="8.5" fill={`url(#${shade})`} />
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
  // While the run plays, the two newest speakers; once it is over, the one line that matters.
  const bubbles = crewBubbles(floor, cast, floor.phase === "done" ? 1 : BUBBLES_MAX);
  const slots = bubbleSlots(bubbles, cast);
  const speakers = new Set(bubbles.map((b) => b.deskId));
  const filed = reported(floor);
  const uid = useId().replace(/[^A-Za-z0-9_-]/g, "");
  const ids = useMemo<GradIds>(
    () => ({
      sky: `cs-sky-${uid}`,
      sun: `cs-sun-${uid}`,
      haze: `cs-haze-${uid}`,
      shade: `cs-shade-${uid}`,
    }),
    [uid],
  );
  // Where each name tag goes: worked out from who is on stage, so it holds all run.
  const names = tagged.map((a) => ({
    id: a.id,
    name: shortName(a.card.name),
    model: a.desk!.model === "code" ? w.code : a.desk!.model,
  }));
  const layoutKey = names.map((n) => `${n.id}:${n.name}:${n.model}`).join("|");
  const layout = useMemo(
    () => tagLayout(cast, new Map(names.map((n) => [n.id, n]))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [layoutKey],
  );
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
      if (!member || (member.place !== "ring" && member.place !== "wing")) continue;
      const hand: [number, number] = [member.sx, member.sy - 34 * member.scale];
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
          <Setting ids={ids} />
          {far.map((a) => (
            <Figure
              key={a.id}
              actor={a}
              notes={onDesk}
              shade={ids.shade}
              speaking={speakers.has(a.id)}
              onPick={onPick}
            />
          ))}
          <Home />
          {near.map((a) => (
            <Figure
              key={a.id}
              actor={a}
              notes={onDesk}
              shade={ids.shade}
              speaking={speakers.has(a.id)}
              onPick={onPick}
            />
          ))}
          {bench.map((a) => (
            <Figure key={a.id} actor={a} notes={[]} shade={ids.shade} />
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
      </div>

      {/* The words on the stage. Every box comes from crewLayout.ts, so none touches another:
          one name tag per member, speech in two slots over the sky, the stamp beside the desk,
          the bench's line. On a phone they leave the stage and sit under it, in that order. */}
      <div className="cs-over" style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}>
        <ol className="cs-tags" aria-label={w.team}>
          {tagged.map((a) => {
            const desk = a.desk!;
            const box = layout.get(a.id);
            const body = (
              <>
                <span className="cs-tag-name">
                  <Badge id={a.id} size={22} />
                  <span>
                    {nameLines(shortName(a.card.name)).map((line) => (
                      <span key={line}>{line}</span>
                    ))}
                  </span>
                </span>
                <span className="cs-tag-model" title={w.runsOn} data-testid="node-model">
                  {desk.model === "code" ? w.code : desk.model}
                </span>
                <span className="cs-tag-state" data-testid="node-state">
                  {deskWord(desk, lang)}
                </span>
              </>
            );
            return (
              <li
                key={a.id}
                className="cs-tag"
                style={box ? place(box) : undefined}
                data-place={a.place}
                data-who={a.id}
                data-agent={a.id}
                data-state={a.state}
                data-tone={a.tone}
                data-speaking={speakers.has(a.id) ? "yes" : "no"}
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
          {bubbles.map((b, i) => {
            const a = spot(b.deskId)!;
            const desk = a.desk!;
            const slot = SLOTS[slots[i] ?? "left"];
            return (
              <p
                key={`${b.deskId}-${b.kind}`}
                className="cs-bubble"
                style={{ ...place(slot), height: undefined, maxHeight: pct(slot.h, VIEW.h) }}
                data-testid="crew-bubble"
                data-agent={b.deskId}
                data-who={b.deskId}
                data-kind={b.kind}
                data-tone={b.tone}
                data-slot={slots[i]}
              >
                <span className="cs-bubble-who">
                  <Badge id={b.deskId} size={24} />
                  {shortName(a.card.name)}
                </span>
                {b.kind === "finding" ? (
                  <span className="cs-bubble-state">{deskWord(desk, lang)}</span>
                ) : null}
                <span className="cs-bubble-text">
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
            style={place(STAMP)}
            data-testid="crew-verdict"
            data-verdict={verdictTone}
            data-stamped={stamped ? "yes" : "no"}
            aria-hidden="true"
          >
            <span>{floor.verdict.headline}</span>
          </p>
        ) : null}

        {bench.length > 0 ? (
          <p className="cs-bench" style={place(BENCH_LINE)} data-testid="team-not-needed">
            <span className="cs-bench-why">{w.notNeeded}: </span>
            {bench.map((a) => a.card.name).join(", ")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

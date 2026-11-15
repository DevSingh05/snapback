// The check team as a live graph: the Planner at the top, the members this ad needed in the
// middle, the Decider at the bottom, joined by square lines. When work reaches a member a dot
// runs to it from the Planner along its line; when the member reports, a dot runs on to the
// Decider. Every dot is set off by a recorded step changing a member's state, once. A member's
// state is the frame of its mark and the line of words under it. With reduced motion (or when
// nothing is playing) there are no dots, only the states.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import "./proofroom.css";
import { deskWord } from "./AgentStrip";
import { AVATAR, Avatar } from "./Avatar";
import { graphLayout, type Spot } from "./graph";
import type { Desk, Lang } from "./model";

export const DEFAULT_WIDTH = 360;

interface Dot {
  id: number;
  path: string;
  out: boolean;
}

/** "Phone and office agent" -> "Phone and office": the mark already says it is a member. */
export function shortName(name: string): string {
  const bare = name.replace(/ agent$/i, "").replace(/^Agente (del |de )?/i, "");
  return bare.charAt(0).toUpperCase() + bare.slice(1);
}

/** What ran a member, for its chip: nothing for code; else the model, by family on a small mark. */
export function modelChip(desk: Desk, wide: boolean): string | null {
  if (desk.model === "code" || desk.state === "unused") return null;
  return wide ? desk.model : desk.model.replace(/^Claude /, "");
}

function Node({
  desk,
  spot,
  width,
  wide,
  lang,
  onPick,
}: {
  desk: Desk;
  spot: Spot;
  width: number;
  wide: boolean;
  lang: Lang;
  onPick?: (id: string) => void;
}) {
  const word = deskWord(desk, lang);
  const style: CSSProperties = wide
    ? { left: spot.x - AVATAR / 2, top: spot.y }
    : { left: spot.x - width / 2, top: spot.y, width };
  const chip = modelChip(desk, wide);
  const body = (
    <>
      <span className="pr-node-mark">
        <Avatar id={desk.card.id} />
        {chip && !wide ? (
          <span className="pr-node-model ui-mono" data-testid="node-model">
            {chip}
          </span>
        ) : null}
      </span>
      <span className="pr-node-text">
        <span className="pr-node-name">
          {shortName(desk.card.name)}
          {chip && wide ? (
            <span className="pr-node-model ui-mono" data-testid="node-model">
              {chip}
            </span>
          ) : null}
        </span>
        <span className="pr-node-role">{desk.card.role}</span>
        <span className="pr-node-state ui-mono" data-testid="node-state">
          {word}
        </span>
      </span>
    </>
  );
  const shared = {
    className: wide ? "pr-node pr-node-wide" : "pr-node",
    style,
    "data-state": desk.state,
    "data-tone": desk.tone,
    "data-agent": desk.card.id,
    "data-testid": "team-node",
  };
  return onPick ? (
    <li {...shared}>
      <button type="button" onClick={() => onPick(desk.card.id)}>
        {body}
      </button>
    </li>
  ) : (
    <li {...shared}>
      <span className="pr-node-in">{body}</span>
    </li>
  );
}

export function TeamGraph({
  desks,
  lang = "en",
  label,
  moving,
  onPick,
}: {
  // The Planner, the members in the order they acted, and the Decider (model.teamView).
  desks: Desk[];
  lang?: Lang;
  label: string;
  // A run is playing and motion is allowed: hand-offs may show as travelling dots.
  moving: boolean;
  onPick?: (deskId: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => {
      const w = Math.round(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, []);

  const planner = desks.find((d) => d.card.team === "planner");
  const decider = desks.find((d) => d.card.team === "decider");
  const members = desks.filter((d) => d.card.team !== "planner" && d.card.team !== "decider");
  const ids = members.map((d) => d.card.id).join(",");
  const layout = useMemo(
    () =>
      graphLayout(
        width,
        planner?.card.id ?? "planner",
        ids ? ids.split(",") : [],
        decider?.card.id ?? "decider",
      ),
    [width, ids, planner?.card.id, decider?.card.id],
  );

  // Hand-offs, from state changes only.
  const seen = useRef<Record<string, string> | null>(null);
  const nextId = useRef(0);
  const [dots, setDots] = useState<Dot[]>([]);
  const states = members.map((d) => `${d.card.id}:${d.state}`).join(",");
  useEffect(() => {
    const before = seen.current;
    const now: Record<string, string> = {};
    const fresh: Dot[] = [];
    for (const d of members) {
      const id = d.card.id;
      now[id] = d.state;
      if (!before || !moving || before[id] === d.state) continue;
      if (d.state === "working" && planner && layout.inPath[id])
        fresh.push({ id: nextId.current++, path: layout.inPath[id], out: false });
      if (d.state === "done" && decider && layout.outPath[id])
        fresh.push({ id: nextId.current++, path: layout.outPath[id], out: true });
    }
    seen.current = now;
    if (fresh.length > 0) setDots((old) => [...old.slice(-10), ...fresh]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [states, moving]);
  useEffect(() => {
    if (!moving) setDots([]);
  }, [moving]);

  const spotOf = (id: string) => layout.members.find((m) => m.id === id)!;
  return (
    <div
      className="pr-graph"
      ref={box}
      style={{ height: layout.height }}
      data-testid="team-graph"
      data-moving={moving ? "yes" : "no"}
    >
      <svg
        className="pr-wires"
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        aria-hidden="true"
        focusable="false"
      >
        {members.map((d) => (
          <g key={d.card.id} data-state={d.state} data-tone={d.tone}>
            <path className="pr-wire" d={layout.inPath[d.card.id]} />
            <path className="pr-wire" d={layout.outPath[d.card.id]} />
          </g>
        ))}
        {/* Lit lines go on top of the quiet ones, so a shared rail shows the newest hand-off. */}
        {members.map((d) => (
          <g key={d.card.id} data-state={d.state} data-tone={d.tone}>
            {d.state === "working" || d.state === "done" ? (
              <path
                className="pr-wire pr-wire-in"
                d={layout.inPath[d.card.id]}
                data-testid="wire-in"
              />
            ) : null}
            {d.state === "done" ? (
              <path
                className="pr-wire pr-wire-out"
                d={layout.outPath[d.card.id]}
                data-testid="wire-out"
              />
            ) : null}
          </g>
        ))}
      </svg>
      {dots.map((dot) => (
        <span
          key={dot.id}
          className={dot.out ? "pr-dot pr-dot-out" : "pr-dot"}
          aria-hidden="true"
          data-testid="team-dot"
          style={{ offsetPath: `path("${dot.path}")` }}
          onAnimationEnd={() => setDots((old) => old.filter((q) => q.id !== dot.id))}
        />
      ))}
      <ol className="pr-nodes" aria-label={label}>
        {planner ? (
          <Node
            desk={planner}
            spot={layout.planner}
            width={layout.colWidth}
            wide
            lang={lang}
            onPick={onPick}
          />
        ) : null}
        {members.map((d) => (
          <Node
            key={d.card.id}
            desk={d}
            spot={spotOf(d.card.id)}
            width={layout.colWidth}
            wide={false}
            lang={lang}
            onPick={onPick}
          />
        ))}
        {decider ? (
          <Node
            desk={decider}
            spot={layout.decider}
            width={layout.colWidth}
            wide
            lang={lang}
            onPick={onPick}
          />
        ) : null}
      </ol>
    </div>
  );
}

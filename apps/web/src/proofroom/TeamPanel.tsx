// "Your check team", open beside the 3D twin (below it on a phone). One status line that moves
// with every step, the team as a row of lights, the thread of what each member says as it
// works, then the Decider's stamp with the card's own verdict. "Meet the team" holds each
// member's card: its job, tools and sources, what runs it, what it never does, and on a case
// what it found with the evidence behind it.
//
// Everything on screen is tied to a recorded step. A finished run replays from its timeline;
// a run that is still live shows steps as the API reports them. With reduced motion there is no
// replay clock and no movement, only the states. Nothing here works out a result.
import { useEffect, useRef, useState } from "react";

import "../ui/ui.css";
import "../case/case.css";
import "./proofroom.css";
import { dataMode } from "../api";
import { tookText } from "../case/answer";
import { VERDICT_TONE } from "../case/model";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { Tag } from "../ui/Tag";
import { Badge, CastPoster } from "./Badge";
import { CrewScene } from "./CrewScene";
import {
  floorAt,
  statusLine,
  teamView,
  type Desk,
  type Floor,
  type Lang,
  type Roster,
} from "./model";
import { TeamGraph } from "./TeamGraph";
import { usePlayer, type Speed } from "./usePlayer";
import { useRoster, useRun, type Run } from "./useRun";
import { WORDS, type RoomWords } from "./words";

/** Where "See how they got this" goes: the report's "How we got this answer". */
export const answerHref = (caseId: string) =>
  `/case/${encodeURIComponent(caseId)}#case-answer-title`;

function DeskCard({
  desk,
  lang,
  w,
  rest,
  focused,
}: {
  desk: Desk;
  lang: Lang;
  w: RoomWords;
  rest: boolean;
  focused: boolean;
}) {
  const { card } = desk;
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!focused) return;
    ref.current?.focus();
    ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [focused]);
  return (
    <article
      ref={ref}
      id={`desk-${card.id}`}
      className="pr-desk"
      data-state={rest ? "rest" : desk.state}
      data-tone={desk.tone}
      data-testid="desk"
      data-agent={card.id}
      tabIndex={-1}
    >
      <header className="pr-desk-head">
        <h4>
          <Badge id={card.id} size={36} />
          {card.name}
        </h4>
        <span className="pr-model ui-mono" title={w.runsOn}>
          {desk.model === "code" ? w.code : desk.model}
        </span>
      </header>
      <p className="pr-job">{card.job}</p>
      <ul className="pr-tools" aria-label="Tools and sources">
        {card.tools.map((tool) => (
          <li key={tool} className="ui-mono">
            {tool}
          </li>
        ))}
      </ul>
      {card.availability ? <p className="pr-avail">{card.availability}</p> : null}
      <p className="pr-never">
        <span className="ui-mono">{w.never}</span> {card.never.join(" · ")}
      </p>
      {rest ? null : (
        <div className="pr-out" data-testid="desk-out">
          {desk.state === "working" ? (
            <p className="pr-now">{card.doing}…</p>
          ) : desk.state === "done" ? (
            <>
              {desk.findings.length > 0 ? (
                <ul className="pr-findings">
                  {desk.findings.map((f) => (
                    <li key={`${f.label}-${f.text}`} data-testid="desk-finding">
                      {f.label ? <b>{f.label}: </b> : null}
                      {f.text}
                    </li>
                  ))}
                </ul>
              ) : desk.byCode ? (
                <p className="pr-quiet">{w.codePlan}</p>
              ) : desk.why ? (
                <p className="pr-quiet">
                  {w.notChecked}: {desk.why}
                </p>
              ) : (
                <ul className="pr-findings pr-did">
                  {desk.evidence.map((line, i) => (
                    <li key={`${line}-${i}`}>{line}</li>
                  ))}
                </ul>
              )}
              {desk.evidence.length > 0 && (desk.findings.length > 0 || desk.why) ? (
                <details className="pr-evidence" data-testid="desk-evidence">
                  <summary>{w.evidence}</summary>
                  <ul>
                    {desk.evidence.map((line, i) => (
                      <li key={`${line}-${i}`}>{line}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
              <p className="pr-foot ui-mono">
                {desk.source ? <Tag source={desk.source} /> : null}
                {desk.tookMs !== null ? <span>{tookText(desk.tookMs, lang)}</span> : null}
              </p>
            </>
          ) : desk.state === "skipped" ? (
            <p className="pr-quiet">
              {w.notChecked}
              {desk.why ? `: ${desk.why}` : ""}
            </p>
          ) : (
            <p className="pr-quiet">{desk.state === "unused" ? w.state.unused : w.waiting}</p>
          )}
        </div>
      )}
    </article>
  );
}

function MeetTheTeam({
  roster,
  floor,
  lang,
  w,
  focus,
}: {
  roster: Roster;
  floor: Floor;
  lang: Lang;
  w: RoomWords;
  focus: string | null;
}) {
  return (
    <div className="pr-meet" data-testid="meet-the-team">
      <CastPoster agents={roster.agents} label={w.team} />
      {roster.teams.map((team) => (
        <section key={team.id} className="pr-team" data-team={team.id}>
          <header className="pr-team-head">
            <h3>{team.name}</h3>
            <p>{team.about}</p>
          </header>
          {floor.desks
            .filter((d) => d.card.team === team.id)
            .map((desk) => (
              <DeskCard
                key={desk.card.id}
                desk={desk}
                lang={lang}
                w={w}
                rest={floor.phase === "rest"}
                focused={focus === desk.card.id}
              />
            ))}
        </section>
      ))}
    </div>
  );
}

export interface TeamPanelProps {
  caseId: string;
  // Tests and stories: a run instead of the reads, no replay on arrival, or no motion.
  run?: Run;
  roster?: Roster;
  autoplay?: boolean;
  reduced?: boolean;
}

export function TeamPanel({
  caseId,
  run: given,
  roster: givenRoster,
  autoplay = true,
  reduced: forced,
}: TeamPanelProps) {
  const prefers = usePrefersReducedMotion();
  const reduced = forced ?? prefers;
  const read = useRun(given ? null : caseId);
  const run = given ?? read;
  const lang: Lang = run.card?.lang === "es" ? "es" : "en";
  const fetched = useRoster(lang);
  const roster = givenRoster ?? fetched;
  const w = WORDS[lang];
  const player = usePlayer(run.timeline, { auto: autoplay, still: reduced });
  const floor = floorAt({
    roster,
    card: run.card,
    timeline: run.timeline,
    listing: run.listing,
    at: player.at,
    snapback: w.snapback,
    hold: run.settling,
  });
  // The same run with every step played: who this ad needed, and the room the end will take.
  const whole = floorAt({
    roster,
    card: run.card,
    timeline: run.timeline,
    listing: run.listing,
    snapback: w.snapback,
    hold: run.settling,
  });
  const team = teamView(floor, whole);
  const ending = floor.verdict ?? (whole.phase === "done" ? whole.verdict : null);
  const [tab, setTab] = useState<"live" | "team">("live");
  // The crew is the Live view; the diagram of the same run stays one press away.
  const [view, setView] = useState<"crew" | "diagram">("crew");
  const [focus, setFocus] = useState<string | null>(null);
  const moving = !reduced && floor.phase === "running";

  // The thread keeps its newest line in view, inside its own box: the page never jumps.
  const thread = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const el = thread.current;
    if (el && moving) el.scrollTop = el.scrollHeight;
  }, [floor.log.length, moving]);

  const source = floor.source ?? run.card?.source ?? dataMode();
  const status =
    run.status === "missing"
      ? w.missing
      : run.status === "locked"
        ? w.locked
        : statusLine(floor, w);
  const speeds: Speed[] = [1, 2];
  const openDesk = (id: string) => {
    setTab("team");
    setFocus(id);
  };

  return (
    <section
      className="pr-panel"
      aria-labelledby="pr-title"
      data-testid="team-panel"
      data-phase={floor.phase}
      data-still={reduced ? "yes" : "no"}
    >
      <header className="pr-head">
        <p className="pr-eyebrow ui-mono">
          <span>{w.room}</span>
          <Tag source={source} testId="team-source" />
        </p>
        <h2 id="pr-title">{w.team}</h2>
        <p className="pr-status" role="status" aria-live="polite" data-testid="team-status">
          {status}
        </p>
        <div className="pr-bar" aria-hidden="true">
          <span style={{ transform: `scaleX(${floor.progress})` }} />
        </div>
        <div
          className="pr-decider"
          data-stamped={floor.verdict ? "yes" : "no"}
          data-verdict={run.card ? VERDICT_TONE[run.card.state] : "slate"}
          data-testid="team-decider"
        >
          <p className="pr-who ui-mono">
            {floor.desks.find((d) => d.card.team === "decider")?.card.name}
          </p>
          {/* The slot is already as tall as the stamp will be, so the stamp lands in place. */}
          <div className="pr-stamp-slot">
            {floor.verdict ? (
              <p className="pr-stamp" data-testid="team-verdict">
                {floor.verdict.headline}
              </p>
            ) : (
              <>
                {ending ? (
                  <p className="pr-stamp pr-held" aria-hidden="true">
                    {ending.headline}
                  </p>
                ) : null}
                <p className="pr-quiet">{floor.phase === "rest" ? w.rest : w.deciderWaits}</p>
              </>
            )}
          </div>
          <p className="pr-rule">{w.deciderRule}</p>
        </div>
      </header>

      <div className="pr-tabs" role="tablist" aria-label={w.team}>
        <button
          type="button"
          role="tab"
          id="pr-tab-live"
          aria-selected={tab === "live"}
          aria-controls="pr-pane-live"
          onClick={() => setTab("live")}
        >
          {w.liveTab}
        </button>
        <button
          type="button"
          role="tab"
          id="pr-tab-team"
          aria-selected={tab === "team"}
          aria-controls="pr-pane-team"
          onClick={() => setTab("team")}
          data-testid="team-tab-meet"
        >
          {w.meet}
        </button>
      </div>

      <div
        id="pr-pane-live"
        role="tabpanel"
        aria-labelledby="pr-tab-live"
        className="pr-pane"
        hidden={tab !== "live"}
      >
        <div className="pr-view" role="group" aria-label={w.view}>
          {(["crew", "diagram"] as const).map((v) => (
            <button
              key={v}
              type="button"
              className="pr-btn pr-btn-quiet"
              aria-pressed={view === v}
              onClick={() => setView(v)}
            >
              {v === "crew" ? w.crewView : w.diagramView}
            </button>
          ))}
        </div>
        {view === "crew" ? (
          <CrewScene
            floor={floor}
            team={team}
            w={w}
            lang={lang}
            moving={moving}
            verdictTone={run.card ? VERDICT_TONE[run.card.state] : "slate"}
            onPick={openDesk}
          />
        ) : (
          <>
            <TeamGraph
              desks={team.shown}
              lang={lang}
              label={w.team}
              moving={moving}
              onPick={openDesk}
            />
            {team.notNeeded.length > 0 ? (
              <p className="pr-quiet" data-testid="team-not-needed">
                {w.notNeeded}: {team.notNeeded.map((a) => a.name).join(", ")}
              </p>
            ) : null}
          </>
        )}
        {run.timeline ? (
          <div className="pr-controls">
            <button
              type="button"
              className="pr-btn"
              onClick={player.replay}
              data-testid="team-replay"
            >
              {w.replay}
            </button>
            <span className="pr-speed" role="group" aria-label={w.speed}>
              {speeds.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="pr-btn pr-btn-quiet"
                  aria-pressed={player.speed === s}
                  onClick={() => player.setSpeed(s)}
                >
                  {s}x
                </button>
              ))}
            </span>
            <button
              type="button"
              className="pr-btn pr-btn-quiet"
              onClick={player.skip}
              disabled={!player.playing}
              data-testid="team-skip"
              aria-label={w.skip}
            >
              {w.skipShort}
            </button>
          </div>
        ) : null}
        {run.timeline ? <p className="pr-note">{w.held}</p> : null}

        <h3 className="pr-sub ui-mono">{w.thread}</h3>
        <ol
          className="pr-thread"
          ref={thread}
          data-testid="team-thread"
          tabIndex={0}
          aria-label={w.thread}
        >
          {floor.log.length === 0 ? <li className="pr-quiet">{w.threadEmpty}</li> : null}
          {floor.log.map((line, i) => (
            <li
              key={`${line.step}-${i}`}
              className="pr-line"
              data-finding={line.finding ? "yes" : "no"}
              data-tone={line.tone ?? "none"}
              data-skipped={line.skipped ? "yes" : "no"}
              data-testid="team-line"
            >
              <span className="pr-who ui-mono">
                {line.deskId ? <Badge id={line.deskId} size={18} /> : null}
                {line.who}
              </span>
              <span className="pr-said">{line.text}</span>
              {line.finding ? null : (
                <span className="pr-foot ui-mono">
                  <Tag source={line.source} />
                  {line.deskId && !line.skipped ? <span>{tookText(line.tookMs, lang)}</span> : null}
                </span>
              )}
            </li>
          ))}
        </ol>
        {floor.fellBack ? <p className="pr-note">{w.fellBack}</p> : null}

        {/* The reasons hold their room from the start of a replay and show with the stamp. */}
        {ending ? (
          <div
            className="pr-because"
            data-shown={floor.verdict ? "yes" : "no"}
            inert={!floor.verdict}
            aria-hidden={!floor.verdict}
          >
            {ending.reasons.length > 0 ? (
              <>
                <p className="pr-who ui-mono">{w.because}</p>
                <ul className="pr-reasons">
                  {ending.reasons.map((reason) => {
                    const desk = floor.desks.find((d) => d.card.id === reason.deskId);
                    return (
                      <li key={reason.text} data-testid={floor.verdict ? "team-reason" : undefined}>
                        <span>{reason.text}</span>
                        {desk ? (
                          <a
                            className="case-text-link"
                            href={`#desk-${desk.card.id}`}
                            data-testid={floor.verdict ? "team-reason-link" : undefined}
                            onClick={(e) => {
                              e.preventDefault();
                              openDesk(desk.card.id);
                            }}
                          >
                            {w.see} {desk.card.name}
                          </a>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </>
            ) : null}
            <a
              className="pr-btn pr-btn-link"
              href={answerHref(caseId)}
              data-testid={floor.verdict ? "team-how" : undefined}
            >
              {w.how} <span aria-hidden="true">→</span>
            </a>
          </div>
        ) : null}
      </div>
      <div
        id="pr-pane-team"
        role="tabpanel"
        aria-labelledby="pr-tab-team"
        className="pr-pane"
        hidden={tab !== "team"}
      >
        <MeetTheTeam
          roster={roster}
          floor={floor}
          lang={lang}
          w={w}
          focus={tab === "team" ? focus : null}
        />
      </div>
    </section>
  );
}

// Home, while a check runs and right after: "Your check team is on it", one light per member.
// Before the case exists nothing is known, so every member waits; no light is ever guessed.
// Once it does, the lights are the case's recorded steps (read again each second while the
// agent is still running), and "Watch them work" opens the live check screen for that case.
import "./proofroom.css";
import { AgentStrip } from "./AgentStrip";
import { bundledRoster, floorAt, statusLine, type Lang } from "./model";
import { teamHref } from "./ReportTeam";
import { useRun } from "./useRun";
import { WORDS } from "./words";

export function HomeTeam({ caseId, lang = "en" }: { caseId: string | null; lang?: Lang }) {
  const run = useRun(caseId, lang);
  const w = WORDS[lang];
  const floor = floorAt({ roster: bundledRoster(lang), card: run.card, timeline: run.timeline });
  // The check team and the Decider; the listing helpers are not part of a check.
  const team = floor.desks.filter(
    (d) => d.card.team === "decider" || (d.card.team === "scam_check" && d.state !== "unused"),
  );
  const done = floor.phase === "done";
  return (
    <section
      className="pr-home"
      aria-label={w.team}
      data-testid="home-team"
      data-phase={floor.phase}
    >
      <p className="pr-home-line">
        <b>{done ? w.team : w.onIt}</b>
        {floor.phase === "rest" ? null : (
          <span data-testid="home-team-status"> · {statusLine(floor, w)}</span>
        )}
      </p>
      <AgentStrip desks={team} lang={lang} label={w.team} />
      {caseId && run.timeline ? (
        <a className="pr-home-link" href={teamHref(caseId)} data-testid="home-team-link">
          {w.watch} <span aria-hidden="true">→</span>
        </a>
      ) : null}
    </section>
  );
}

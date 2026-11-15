// The report's strip, right under the verdict: "Your check team: 6 checked, 2 found red flags"
// with each member's light, and "See your check team work" into the live check screen.
// It reads the same card and timeline the report already has. No timeline: it is not there.
import type { Card, CaseTimeline, RealListing } from "../contracts";
import { AgentStrip } from "./AgentStrip";
import { bundledRoster, floorAt, teamSummary, type Lang } from "./model";
import { WORDS } from "./words";

/** The live check screen for a case: the 3D twin with the check team open beside it. */
export const teamHref = (caseId: string) => `/case/${encodeURIComponent(caseId)}/twin`;

export function ReportTeam({
  card,
  timeline,
  realListing = null,
}: {
  card: Card;
  timeline: CaseTimeline | null;
  realListing?: RealListing | null;
}) {
  if (!timeline || timeline.steps.length === 0) return null;
  const lang: Lang = card.lang === "es" ? "es" : "en";
  const w = WORDS[lang];
  const floor = floorAt({ roster: bundledRoster(lang), card, timeline, listing: realListing });
  const { checked, redFlags } = teamSummary(floor);
  const team = floor.desks.filter((d) => d.card.team === "scam_check" && d.state !== "unused");
  return (
    <section className="pr-report" aria-label={w.team} data-testid="report-team">
      <p className="pr-report-line">
        <b>{w.team}:</b>{" "}
        <span data-testid="report-team-summary">{w.summary(checked, redFlags)}</span>
      </p>
      <AgentStrip desks={team} lang={lang} label={w.team} />
      <a className="case-text-link" href={teamHref(card.case_id)} data-testid="report-team-link">
        {w.seeTeam} <span aria-hidden="true">→</span>
      </a>
    </section>
  );
}

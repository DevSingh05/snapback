import cardHold from "../../../fixtures/contracts/card_hold.json";
import type { Card } from "./contracts";

const fixtureCard = cardHold as Card;

export class CaseNotFound extends Error {}

// VITE_API_URL unset means fixture mode: the synthetic card in fixtures/contracts is served
// for its own case id only, and its source field says "fixture", so the page shows FIXTURE.
export async function fetchCard(caseId: string, signal?: AbortSignal): Promise<Card> {
  const base = import.meta.env.VITE_API_URL as string | undefined;
  if (!base) {
    if (caseId.toUpperCase() === fixtureCard.case_id) return fixtureCard;
    throw new CaseNotFound(caseId);
  }
  const res = await fetch(`${base.replace(/\/$/, "")}/cases/${encodeURIComponent(caseId)}/card`, {
    signal,
  });
  if (res.status === 404) throw new CaseNotFound(caseId);
  if (!res.ok) throw new Error(`The server answered ${res.status}.`);
  return (await res.json()) as Card;
}

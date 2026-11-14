import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { DataSource } from "../contracts";

export interface CreatedCase {
  case_id: string;
  source: DataSource;
  // The live-check message the renter may forward to the poster. Nothing is sent until the
  // renter approves it and sends it themselves.
  challenge_text: string;
}

export interface CaseInput {
  link: string | null;
  text: string | null;
  files: File[];
}

// Fixture mode unless VITE_API_URL is set. Every screen shows this as a LIVE or FIXTURE chip.
export const MODE: DataSource = import.meta.env.VITE_API_URL ? "live" : "fixture";

export const FIXTURE_CHALLENGE_TEXT =
  "Hi! Before I book a viewing, could you send me a photo of the front door of the unit, taken right now, with today's date written on a piece of paper in the shot? Thanks!";

export type CreateCase = (input: CaseInput, signal?: AbortSignal) => Promise<CreatedCase>;

// POST /cases is not in the API yet (src/snapback/api has /healthz and /verdict only). With
// VITE_API_URL unset this returns the synthetic fixture case so the flow runs end to end.
// With it set, it posts multipart form data to {VITE_API_URL}/cases and expects CreatedCase.
export const createCase: CreateCase = async (input, signal) => {
  const base = import.meta.env.VITE_API_URL as string | undefined;
  if (!base) {
    await new Promise((r) => setTimeout(r, 700));
    return {
      case_id: (cardHold as { case_id: string }).case_id,
      source: "fixture",
      challenge_text: FIXTURE_CHALLENGE_TEXT,
    };
  }
  const body = new FormData();
  if (input.link) body.append("link", input.link);
  if (input.text) body.append("text", input.text);
  for (const f of input.files) body.append("photos", f, f.name);
  const res = await fetch(`${base.replace(/\/$/, "")}/cases`, { method: "POST", body, signal });
  if (!res.ok) throw new Error(`The server answered ${res.status}. Try again in a moment.`);
  return (await res.json()) as CreatedCase;
};

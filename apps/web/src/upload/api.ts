import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { apiFetch, dataMode, saveCaseReadToken, saveCaseToken } from "../api";
import type { DataSource } from "../contracts";

export interface CreatedCase {
  case_id: string;
  source: DataSource;
  // The live-check message the renter may forward to the poster. Nothing is sent until the
  // renter approves it and sends it themselves. null: no check applies (for example the
  // listing is out of scope), so the flow goes straight to the card.
  challenge_text: string | null;
}

export interface CaseInput {
  link: string | null;
  text: string | null;
  files: File[];
}

export type CaseProgress = "running" | "waiting_for_approval" | "done";

export interface CaseStatus {
  case_id: string;
  source: DataSource;
  status: CaseProgress;
  state: string | null;
}

// Fixture mode unless the API is configured. Every screen shows this as a LIVE or FIXTURE chip.
export const MODE: DataSource = dataMode();

export const FIXTURE_CHALLENGE_TEXT =
  "Hi! Before I book a viewing, could you send me a photo of the front door of the unit, taken right now, with today's date written on a piece of paper in the shot? Thanks!";

export type CreateCase = (input: CaseInput, signal?: AbortSignal) => Promise<CreatedCase>;
export type Decision = "send" | "edit" | "cancel";
export type ApproveChallenge = (caseId: string, decision: Decision, text?: string) => Promise<void>;
export type GetCaseStatus = (caseId: string, signal?: AbortSignal) => Promise<CaseStatus>;

async function failure(res: Response): Promise<Error> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = ` ${body.detail}`;
  } catch {
    // not JSON; the status is enough
  }
  return new Error(`The server answered ${res.status}.${detail}`.trim());
}

// POST /cases (multipart: link, text, photos). Keeps the returned case token for later writes.
// With the API unset it returns the synthetic fixture case so the flow runs end to end.
export const createCase: CreateCase = async (input, signal) => {
  if (dataMode() === "fixture") {
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
  const res = await apiFetch("/cases", { method: "POST", body, signal });
  if (!res.ok) throw await failure(res);
  const made = (await res.json()) as {
    case_id: string;
    source: DataSource;
    token: string;
    read_token?: string | null;
    challenge_text?: string | null;
  };
  saveCaseToken(made.case_id, made.token);
  if (made.read_token) saveCaseReadToken(made.case_id, made.read_token);
  return {
    case_id: made.case_id,
    source: made.source,
    challenge_text: made.challenge_text ?? null,
  };
};

// POST /cases/{id}/challenge/approve with the case token. Live mode only.
export const approveChallenge: ApproveChallenge = async (caseId, decision, text) => {
  const res = await apiFetch(`/cases/${encodeURIComponent(caseId)}/challenge/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text === undefined ? { decision } : { decision, text }),
    tokenFor: caseId,
  });
  // 409: the case was already decided (a second click, or another tab). The answer stands, so
  // this counts as success and the page goes on to the case.
  if (res.status === 409) return;
  if (!res.ok) throw await failure(res);
};

// GET /cases/{id}: where the case stands. Live mode only.
export const getCaseStatus: GetCaseStatus = async (caseId, signal) => {
  const res = await apiFetch(`/cases/${encodeURIComponent(caseId)}`, { signal, tokenFor: caseId });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as CaseStatus;
};

// GET /healthz: which data the API itself is serving. A web app wired to an API that runs on
// fixtures must still say FIXTURE, so the chip before a case exists comes from here.
export async function fetchApiSource(signal?: AbortSignal): Promise<DataSource> {
  const res = await apiFetch("/healthz", { signal });
  if (!res.ok) throw await failure(res);
  const body = (await res.json()) as { data_source?: string };
  return body.data_source === "live" ? "live" : "fixture";
}

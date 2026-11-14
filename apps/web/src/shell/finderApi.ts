// The Finder's line to the deep agent (M9, src/snapback/api/finder.py). The session id and its
// token live in sessionStorage for this tab only. The token goes in a header, never in an address.
import { apiBase } from "../api";
import type {
  ChosenBy,
  FinderDecision,
  FinderMessageRequest,
  FinderProposal,
  FinderReply,
  FinderSessionStarted,
  FinderSignal,
  FinderState,
} from "../contracts";

const KEY = "snapback.finder-session";

/** The stamp on every reply, offer, pick and step: who chose it. */
export const STAMP: Record<ChosenBy, string> = {
  model: "Picked by the model",
  policy: "Picked by our rules",
};

export interface FinderAuth {
  sid: string;
  token: string;
}

/** The Finder service is not reachable: the page falls back to its rules on this device. */
export class FinderOffline extends Error {}
/** The server forgot this session (it restarted): start a new one. */
export class FinderGone extends Error {}
/** The last turn is still running on the server (409 on a message). */
export class FinderBusy extends Error {}

export const DAILY_LIMIT = "Daily limit reached; your saved preferences still filter places.";

export function loadAuth(): FinderAuth | null {
  try {
    const raw = JSON.parse(window.sessionStorage.getItem(KEY) ?? "null") as unknown;
    if (raw && typeof raw === "object") {
      const { sid, token } = raw as Record<string, unknown>;
      if (typeof sid === "string" && typeof token === "string") return { sid, token };
    }
  } catch {
    // unreadable or blocked: start fresh
  }
  return null;
}

export function saveAuth(auth: FinderAuth | null): void {
  try {
    if (auth) window.sessionStorage.setItem(KEY, JSON.stringify(auth));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
}

async function call<T>(path: string, init: RequestInit, auth?: FinderAuth): Promise<T> {
  const base = apiBase();
  if (!base) throw new FinderOffline("No API is configured.");
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (auth) headers.set("Authorization", `Bearer ${auth.token}`);
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new FinderOffline("The Finder service did not answer.");
  }
  if (res.status === 404 || res.status === 401 || res.status === 403) {
    if (auth) throw new FinderGone("This Finder session has ended.");
    throw new FinderOffline("The Finder service is not on this server.");
  }
  if (res.status === 409 && path.endsWith("/message"))
    throw new FinderBusy("Still thinking about your last message.");
  if (res.status === 429) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      /minute/i.test(detail) ? "Too many messages. Wait a minute and send again." : DAILY_LIMIT,
    );
  }
  if (res.status >= 500) throw new FinderOffline("The Finder service is not running.");
  if (!res.ok) throw new Error(`The Finder answered ${res.status}.`);
  return (await res.json()) as T;
}

export async function startSession(): Promise<FinderAuth & { started: FinderSessionStarted }> {
  const started = await call<FinderSessionStarted>("/finder/sessions", { method: "POST" });
  const auth = { sid: started.session_id, token: started.token };
  saveAuth(auth);
  return { ...auth, started };
}

export function getState(auth: FinderAuth, signal?: AbortSignal): Promise<FinderState> {
  return call<FinderState>(
    `/finder/${encodeURIComponent(auth.sid)}/state`,
    { method: "GET", signal },
    auth,
  );
}

export function sendMessage(
  auth: FinderAuth,
  text: string | null,
  signals: FinderSignal[],
): Promise<FinderReply> {
  const body: FinderMessageRequest = { signals: signals.slice(0, 20) };
  if (text) body.text = text.slice(0, 500);
  return call<FinderReply>(
    `/finder/${encodeURIComponent(auth.sid)}/message`,
    { method: "POST", body: JSON.stringify(body) },
    auth,
  );
}

export function decide(
  auth: FinderAuth,
  proposalId: string,
  decision: FinderDecision["decision"],
): Promise<FinderProposal> {
  return call<FinderProposal>(
    `/finder/${encodeURIComponent(auth.sid)}/proposals/${encodeURIComponent(proposalId)}`,
    { method: "POST", body: JSON.stringify({ decision }) },
    auth,
  );
}

/** "What I've learned" in plain words. Keys the page does not know are not shown. */
export function learnedLines(learned: Record<string, string | boolean>): string[] {
  const out: string[] = [];
  const of = (v: string | boolean | undefined) => (typeof v === "string" ? v : null);
  const walk = of(learned.passed_walkups);
  if (walk) out.push(`Passed on ${walk} walk-ups`);
  const park = of(learned.passed_no_parking);
  if (park) out.push(`Passed on ${park} places without parking`);
  const scan = of(learned.picked_with_scan);
  if (scan) out.push(`Picked ${scan} places with a 3D scan`);
  const cheap = of(learned.picked_below_budget);
  if (cheap) out.push(`${cheap} picks cost well under your budget`);
  if (learned.said_no_walkup === true) out.push("You said no walk-ups");
  if (learned.said_parking === true) out.push("You asked about parking");
  if (learned.budget_set === true) out.push("You set a budget");
  return out;
}

/** What an accepted proposal keeps, as a chip. */
export function keptLabel(p: FinderProposal): string {
  switch (p.key) {
    case "propose_no_walkup":
      return "No walk-ups";
    case "propose_parking":
      return "Needs parking";
    case "propose_prefer_scans":
      return "3D scans first";
    case "propose_lower_budget":
      return p.update.max_rent
        ? `Under $${p.update.max_rent.toLocaleString("en-US")}`
        : "Lower budget";
  }
}

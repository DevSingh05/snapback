import cardHold from "../../../fixtures/contracts/card_hold.json";
import type { Card, DataSource } from "./contracts";

const fixtureCard = cardHold as Card;

export class CaseNotFound extends Error {}

// VITE_API_URL unset means fixture mode. `make web` sets it to /api, the dev proxy to the API on
// :8000, so the browser stays on one origin and needs no CORS. It can also be a full URL.
export function apiBase(): string | undefined {
  const base = import.meta.env.VITE_API_URL as string | undefined;
  return base ? base.replace(/\/$/, "") : undefined;
}

export function dataMode(): DataSource {
  return apiBase() ? "live" : "fixture";
}

// The per-case secret that POST /cases returns once. It lives in sessionStorage keyed by case id
// and is never put in a URL. Reading a case needs only its id; writing needs this.
const TOKEN_PREFIX = "snapback.case-token.";

export function saveCaseToken(caseId: string, token: string): void {
  try {
    window.sessionStorage.setItem(TOKEN_PREFIX + caseId.toUpperCase(), token);
  } catch {
    // Storage blocked: writes will fail with 401 and the page says so.
  }
}

// The read-only secret (POST /cases `read_token`). Only this one may travel in a URL, for the
// SSE trace, because EventSource cannot send headers. The write token above never does.
const READ_TOKEN_PREFIX = "snapback.case-read-token.";

export function saveCaseReadToken(caseId: string, token: string): void {
  try {
    window.sessionStorage.setItem(READ_TOKEN_PREFIX + caseId.toUpperCase(), token);
  } catch {
    // Storage blocked: the live trace shows its locked state.
  }
}

export function loadCaseReadToken(caseId: string): string | null {
  try {
    return window.sessionStorage.getItem(READ_TOKEN_PREFIX + caseId.toUpperCase());
  } catch {
    return null;
  }
}

export function loadCaseToken(caseId: string): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_PREFIX + caseId.toUpperCase());
  } catch {
    return null;
  }
}

// fetch against the API base, with the client cookie sent, and the case token as a Bearer header
// when the caller names a case to write to.
export function apiFetch(
  path: string,
  init: RequestInit & { tokenFor?: string } = {},
): Promise<Response> {
  const base = apiBase();
  if (!base) return Promise.reject(new Error("No API is configured."));
  const { tokenFor, headers, ...rest } = init;
  const merged = new Headers(headers);
  const token = tokenFor ? loadCaseToken(tokenFor) : null;
  if (token) merged.set("Authorization", `Bearer ${token}`);
  return fetch(`${base}${path}`, { ...rest, headers: merged, credentials: "include" });
}

// GET with the case's read token in the Authorization header (never in a URL; ruling on #113).
// Returns null when this browser holds no read token for the case, so callers fall back to fixtures.
export function apiFetchRead(
  path: string,
  caseId: string,
  init: RequestInit = {},
): Promise<Response> | null {
  const token = loadCaseReadToken(caseId);
  if (!apiBase() || !token) return null;
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return apiFetch(path, { ...init, headers });
}

export async function fetchCard(caseId: string, signal?: AbortSignal): Promise<Card> {
  if (!apiBase()) {
    if (caseId.toUpperCase() === fixtureCard.case_id) return fixtureCard;
    throw new CaseNotFound(caseId);
  }
  const res = await apiFetch(`/cases/${encodeURIComponent(caseId)}/card`, { signal });
  if (res.status === 404) throw new CaseNotFound(caseId);
  if (!res.ok) throw new Error(`The server answered ${res.status}.`);
  return (await res.json()) as Card;
}

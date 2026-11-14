import { apiFetch, apiFetchRead } from "../api";
import type { DataSource } from "../contracts";

// Mirrors snapback/office/models.py. Words come from the API and are shown as given.
export interface OfficeStatus {
  case_id: string;
  source: DataSource;
  domain: string | null;
  offered: boolean;
  confirmed: boolean;
  confirmed_domain: string | null;
  delivery: "outbox";
  guidance: string;
}

export interface OfficeRequested {
  case_id: string;
  source: DataSource;
  domain: string;
  sent: false;
  delivery: "outbox";
  expires_in_minutes: number;
  detail: string;
}

export class NoToken extends Error {}

// null when this browser holds no read token (fixture mode or another device): the panel hides.
export async function fetchOffice(caseId: string): Promise<OfficeStatus | null> {
  const pending = apiFetchRead(`/cases/${encodeURIComponent(caseId)}/office`, caseId);
  if (!pending) return null;
  const res = await pending;
  if (!res.ok) return null;
  return (await res.json()) as OfficeStatus;
}

export async function requestOfficeLink(caseId: string, address: string): Promise<OfficeRequested> {
  const res = await apiFetch(`/cases/${encodeURIComponent(caseId)}/confirm-office`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
    tokenFor: caseId,
  });
  if (res.status === 401) throw new NoToken("This browser does not hold the key for this case.");
  const body = (await res.json().catch(() => ({}))) as {
    detail?: string;
  } & Partial<OfficeRequested>;
  if (!res.ok)
    throw new Error(typeof body.detail === "string" ? body.detail : "That did not work.");
  return body as OfficeRequested;
}

export interface ListingContext {
  building: string | null;
  address: string | null;
  unit: string | null;
  rent: number | null;
  poster: string | null;
  phones: string[];
  emails: string[];
  links: string[];
}

export interface OfficePeek {
  domain: string;
  source: DataSource;
  listing: ListingContext;
}

export interface OfficeAnswered {
  decision: "yes" | "no";
  domain: string;
  message: string;
}

async function postToken<T>(path: string, body: object): Promise<T> {
  // The token travels in the body, never in an address, so no server log holds it.
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as { detail?: string };
  if (!res.ok)
    throw new Error(typeof data.detail === "string" ? data.detail : "That did not work.");
  return data as T;
}

export const peekOffice = (token: string) => postToken<OfficePeek>("/office/peek", { token });

export const answerOffice = (token: string, decision: "yes" | "no") =>
  postToken<OfficeAnswered>("/office/answer", { token, decision });

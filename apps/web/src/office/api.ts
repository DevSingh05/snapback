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

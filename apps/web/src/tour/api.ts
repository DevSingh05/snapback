import { apiBase, apiFetch, apiFetchRead } from "../api";
import type { TourPlan, WalkResponse } from "../contracts";
import { FIXTURE_TOUR } from "./fixtureTour";

export interface TourTarget {
  propertyId: string;
  planKey?: string | null;
  /** A case whose placed ad photos should appear on their rooms (needs its read token). */
  caseId?: string | null;
  /** "elsewhere": walk the building the case's photos were taken in (needs the case). */
  mode?: "claimed" | "elsewhere";
}

/** The tour plan: the API's when one is configured, else the labelled synthetic fixture. */
export async function fetchTour(target: TourTarget, signal?: AbortSignal): Promise<TourPlan> {
  if (!apiBase()) return FIXTURE_TOUR;
  const q = target.planKey ? `?plan_key=${encodeURIComponent(target.planKey)}` : "";
  const place = `/places/${encodeURIComponent(target.propertyId)}/tour${q}`;
  const withCase = target.caseId
    ? apiFetchRead(
        `/cases/${encodeURIComponent(target.caseId)}/walk${target.mode === "elsewhere" ? "?mode=elsewhere" : ""}`,
        target.caseId,
        { signal },
      )
    : null;
  const caseRes = withCase ? await withCase : null;
  if (caseRes?.ok) return ((await caseRes.json()) as WalkResponse).plan;
  const res = await apiFetch(place, { signal });
  if (res.status === 404) throw new Error("No researched place with that id.");
  if (res.status === 422) throw new Error("This building has several floor plans. Pick one first.");
  if (!res.ok) throw new Error(`The tour could not load (${res.status}).`);
  return (await res.json()) as TourPlan;
}

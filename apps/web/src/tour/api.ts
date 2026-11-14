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

export interface TourResult {
  plan: TourPlan;
  /** The Matterport model the case walk was built from; load this one. Case walks only. */
  modelId: string | null;
  /** True when the plan came from the token-gated case walk. */
  fromCase: boolean;
  /** Shown above the tour when the case's own photos could not be loaded. */
  notice: string | null;
}

const NO_CASE_PHOTOS = "The case's photos could not be loaded, so none are placed in these rooms.";

/** The tour: the case walk when a case is named (its model id and placed photos), else the public
 *  place tour, else the labelled synthetic fixture. In elsewhere mode a failed case walk is an
 *  error, never a silent swap to another home's public tour. */
export async function fetchTour(target: TourTarget, signal?: AbortSignal): Promise<TourResult> {
  if (!apiBase()) return { plan: FIXTURE_TOUR, modelId: null, fromCase: false, notice: null };
  const elsewhere = target.mode === "elsewhere";
  let notice: string | null = null;
  if (target.caseId) {
    const path = `/cases/${encodeURIComponent(target.caseId)}/walk${elsewhere ? "?mode=elsewhere" : ""}`;
    const pending = apiFetchRead(path, target.caseId, { signal });
    let res: Response | null = null;
    try {
      res = pending ? await pending : null;
    } catch (e) {
      if (signal?.aborted) throw e;
    }
    if (res?.ok) {
      const body = (await res.json()) as WalkResponse;
      return { plan: body.plan, modelId: body.model_id ?? null, fromCase: true, notice: null };
    }
    if (elsewhere) {
      throw new Error("The building where the photos were taken could not be loaded.");
    }
    notice = NO_CASE_PHOTOS;
  }
  const q = target.planKey ? `?plan_key=${encodeURIComponent(target.planKey)}` : "";
  const res = await apiFetch(`/places/${encodeURIComponent(target.propertyId)}/tour${q}`, {
    signal,
  });
  if (res.status === 404) throw new Error("No researched place with that id.");
  if (res.status === 422) throw new Error("This building has several floor plans. Pick one first.");
  if (!res.ok) throw new Error(`The tour could not load (${res.status}).`);
  return { plan: (await res.json()) as TourPlan, modelId: null, fromCase: false, notice };
}

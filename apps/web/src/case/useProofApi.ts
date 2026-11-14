// The two proof reads for the case page: the real listing and the places that can be handed
// off. Both need the API and the case's read token (in a header, never in an address). With no
// API, no token, or a route that is not there yet, they give nothing and the page stands.
import { useEffect, useState } from "react";

import { apiBase, apiFetchRead } from "../api";
import { fetchAlternatives } from "../search/api";
import type { RealListing, SaferPlace } from "./model";

export function useRealListing(caseId: string): RealListing | null {
  const [listing, setListing] = useState<RealListing | null>(null);
  useEffect(() => {
    if (!apiBase()) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await apiFetchRead(
          `/cases/${encodeURIComponent(caseId)}/real-listing`,
          caseId,
          {
            signal: ctrl.signal,
          },
        );
        if (!res?.ok) return;
        const body = (await res.json()) as RealListing;
        if (!ctrl.signal.aborted) setListing(body);
      } catch {
        // No panel: the rest of the result does not depend on it.
      }
    })();
    return () => ctrl.abort();
  }, [caseId]);
  return listing;
}

export function useSaferPlaces(caseId: string, wanted: boolean): SaferPlace[] {
  const [places, setPlaces] = useState<SaferPlace[]>([]);
  useEffect(() => {
    if (!wanted || !apiBase()) return;
    const ctrl = new AbortController();
    fetchAlternatives(caseId, ctrl.signal)
      .then((found) => {
        if (!ctrl.signal.aborted) setPlaces(found.matches as SaferPlace[]);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [caseId, wanted]);
  return places;
}

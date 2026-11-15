// The report's reads beyond the card: the real listing, the draft note for the leasing office,
// the report pack and the researched places to go to instead. Each is one GET with the case's
// read token in a header (never in an address) and comes back in the API's own shape from
// contracts.ts. With no API, no token, a 404 or any other failure a read gives null, and its
// section of the report is simply not there; the rest of the page does not depend on it.
import { useEffect, useState } from "react";

import { apiBase, apiFetchRead } from "../api";
import type { CaseTimeline, CopyAlert, RealListing, ReportPack } from "../contracts";
import { fetchAlternatives } from "../search/api";
import type { SaferPlace } from "./model";

const langOf = (lang: string | undefined) => (lang === "es" ? "es" : "en");

/** One read of `/cases/{id}/<what>`; null until it lands, and null for good when it does not. */
function useCaseRead<T>(caseId: string, what: string, lang?: string): T | null {
  const [body, setBody] = useState<T | null>(null);
  useEffect(() => {
    setBody(null);
    if (!apiBase()) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await apiFetchRead(
          `/cases/${encodeURIComponent(caseId)}/${what}?lang=${langOf(lang)}`,
          caseId,
          { signal: ctrl.signal },
        );
        if (!res?.ok) return;
        const read = (await res.json()) as T;
        if (!ctrl.signal.aborted) setBody(read);
      } catch {
        // No section: the rest of the report stands without it.
      }
    })();
    return () => ctrl.abort();
  }, [caseId, what, lang]);
  return body;
}

/** GET /cases/{id}/real-listing. A 404 means CoStar has no record of the building: null. */
export function useRealListing(caseId: string, lang?: string): RealListing | null {
  return useCaseRead<RealListing>(caseId, "real-listing", lang);
}

/** GET /cases/{id}/copy-alert: the draft, only when the API says it fires. It is never sent. */
export function useCopyAlert(caseId: string, lang?: string): CopyAlert | null {
  const alert = useCaseRead<CopyAlert>(caseId, "copy-alert", lang);
  return alert?.fires ? alert : null;
}

/** GET /cases/{id}/report: the pack a renter can file. */
export function useReportPack(caseId: string, lang?: string): ReportPack | null {
  return useCaseRead<ReportPack>(caseId, "report", lang);
}

/** GET /cases/{id}/timeline: what the agent did. Null until it lands, and for good if it fails. */
export function useTimeline(caseId: string, lang?: string): CaseTimeline | null {
  return useCaseRead<CaseTimeline>(caseId, "timeline", lang);
}

export function useSaferPlaces(caseId: string, wanted: boolean): SaferPlace[] {
  const [places, setPlaces] = useState<SaferPlace[]>([]);
  useEffect(() => {
    if (!wanted) return;
    const ctrl = new AbortController();
    fetchAlternatives(caseId, ctrl.signal)
      .then((found) => {
        if (!ctrl.signal.aborted) setPlaces(found.matches);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [caseId, wanted]);
  return places;
}

// The report's reads beyond the card: the real listing, the draft note for the leasing office,
// the report pack and the researched places to go to instead. Each is one GET with the case's
// read token in a header (never in an address) and comes back in the API's own shape from
// contracts.ts. With no API, no token, a 404 or any other failure a read gives null, and its
// section of the report is simply not there; the rest of the page does not depend on it. A 202
// means the check is still running: the `...Read` forms say so (`waiting`) while they retry.
import { useEffect, useState } from "react";

import { apiBase, apiFetchReadWhenReady } from "../api";
import type { CaseTimeline, CopyAlert, RealListing, ReportPack } from "../contracts";
import { fetchAlternatives } from "../search/api";
import type { SaferPlace } from "./model";

const langOf = (lang: string | undefined) => (lang === "es" ? "es" : "en");

/** What a read has so far: its body once it lands, and whether the API is still checking. */
export interface Read<T> {
  value: T | null;
  waiting: boolean;
}

/**
 * One read of `/cases/{id}/<what>`. While the API answers 202 (the check is still running) it
 * asks again with a growing wait and reports `waiting`, so the page can say "Still checking…"
 * instead of showing nothing. Null for good when it does not land (a 404, an error, time up).
 */
function useCaseRead<T>(caseId: string, what: string, lang?: string): Read<T> {
  const [read, setRead] = useState<Read<T>>({ value: null, waiting: false });
  useEffect(() => {
    setRead({ value: null, waiting: false });
    if (!apiBase()) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await apiFetchReadWhenReady(
          `/cases/${encodeURIComponent(caseId)}/${what}?lang=${langOf(lang)}`,
          caseId,
          { signal: ctrl.signal },
          (waiting) => {
            if (!ctrl.signal.aborted && waiting) setRead({ value: null, waiting: true });
          },
        );
        if (!res?.ok || res.status === 202) {
          if (!ctrl.signal.aborted) setRead({ value: null, waiting: false });
          return;
        }
        const body = (await res.json()) as T;
        if (!ctrl.signal.aborted) setRead({ value: body, waiting: false });
      } catch {
        // No section: the rest of the report stands without it.
        if (!ctrl.signal.aborted) setRead({ value: null, waiting: false });
      }
    })();
    return () => ctrl.abort();
  }, [caseId, what, lang]);
  return read;
}

/** GET /cases/{id}/real-listing. A 404 means CoStar has no record of the building: null. */
export const useRealListingRead = (caseId: string, lang?: string) =>
  useCaseRead<RealListing>(caseId, "real-listing", lang);
export const useRealListing = (caseId: string, lang?: string): RealListing | null =>
  useRealListingRead(caseId, lang).value;

/** GET /cases/{id}/copy-alert: the draft, only when the API says it fires. It is never sent. */
export function useCopyAlertRead(caseId: string, lang?: string): Read<CopyAlert> {
  const read = useCaseRead<CopyAlert>(caseId, "copy-alert", lang);
  return { value: read.value?.fires ? read.value : null, waiting: read.waiting };
}
export const useCopyAlert = (caseId: string, lang?: string): CopyAlert | null =>
  useCopyAlertRead(caseId, lang).value;

/** GET /cases/{id}/report: the pack a renter can file. */
export const useReportPackRead = (caseId: string, lang?: string) =>
  useCaseRead<ReportPack>(caseId, "report", lang);
export const useReportPack = (caseId: string, lang?: string): ReportPack | null =>
  useReportPackRead(caseId, lang).value;

/** GET /cases/{id}/timeline: what the agent did. Null until it lands, and for good if it fails. */
export const useTimeline = (caseId: string, lang?: string): CaseTimeline | null =>
  useCaseRead<CaseTimeline>(caseId, "timeline", lang).value;

/** GET /cases/{id}/alternatives: `waiting` while the API is still checking. */
export function useSaferPlacesRead(caseId: string, wanted: boolean): Read<SaferPlace[]> {
  const [read, setRead] = useState<Read<SaferPlace[]>>({ value: null, waiting: false });
  useEffect(() => {
    if (!wanted) return;
    const ctrl = new AbortController();
    fetchAlternatives(caseId, ctrl.signal, (waiting) => {
      if (!ctrl.signal.aborted && waiting) setRead({ value: null, waiting: true });
    })
      .then((found) => {
        if (!ctrl.signal.aborted) setRead({ value: found.matches, waiting: false });
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setRead({ value: null, waiting: false });
      });
    return () => ctrl.abort();
  }, [caseId, wanted]);
  return read;
}
export const useSaferPlaces = (caseId: string, wanted: boolean): SaferPlace[] =>
  useSaferPlacesRead(caseId, wanted).value ?? [];

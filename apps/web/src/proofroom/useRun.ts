// What the Proof Room reads: the roster (GET /agents, with the bundled copy until it lands),
// and for a case its card, timeline and real-listing read. The timeline needs the case's read
// token, sent in a header by apiFetchRead and never put in an address. While the API says the
// agent is still running, the timeline is read again every second. Reads only.
import { useEffect, useState } from "react";

import {
  CaseNotFound,
  apiBase,
  apiFetch,
  apiFetchRead,
  fetchCard,
  loadCaseReadToken,
} from "../api";
import type { Card, CaseTimeline, RealListing } from "../contracts";
import { asRoster, bundledRoster, type Roster } from "./model";
import { SAMPLE_ID, sampleCard, sampleTimeline } from "./sample";

export const POLL_MS = 1000;

export function useRoster(lang: string): Roster {
  const [roster, setRoster] = useState<Roster>(() => bundledRoster(lang));
  useEffect(() => {
    setRoster(bundledRoster(lang));
    if (!apiBase()) return;
    const ctrl = new AbortController();
    apiFetch(`/agents?lang=${lang === "es" ? "es" : "en"}`, { signal: ctrl.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((body) => {
        const read = asRoster(body);
        if (read && !ctrl.signal.aborted) setRoster(read);
      })
      .catch(() => {
        // The bundled roster stands.
      });
    return () => ctrl.abort();
  }, [lang]);
  return roster;
}

// none: no case asked for. locked: this browser holds no read token for the case, so its steps
// cannot be read (the card still can). missing: no such case.
export type RunStatus = "none" | "loading" | "ready" | "locked" | "missing";

export interface Run {
  status: RunStatus;
  card: Card | null;
  timeline: CaseTimeline | null;
  listing: RealListing | null;
}

const NONE: Run = { status: "none", card: null, timeline: null, listing: null };

const isRunning = (t: CaseTimeline | null) =>
  (t as (CaseTimeline & { running?: boolean }) | null)?.running === true;

async function readJson<T>(path: string, caseId: string, signal: AbortSignal): Promise<T | null> {
  const res = await apiFetchRead(path, caseId, { signal });
  return res?.ok ? ((await res.json()) as T) : null;
}

export function useRun(caseId: string | null, lang = "en"): Run {
  const [run, setRun] = useState<Run>(caseId ? { ...NONE, status: "loading" } : NONE);
  useEffect(() => {
    if (!caseId) return setRun(NONE);
    const sample =
      caseId === SAMPLE_ID || (!apiBase() && caseId.toUpperCase() === sampleCard.case_id);
    if (sample) {
      return setRun({ status: "ready", card: sampleCard, timeline: sampleTimeline, listing: null });
    }
    if (!apiBase()) return setRun({ ...NONE, status: "missing" });
    setRun({ ...NONE, status: "loading" });
    const ctrl = new AbortController();
    const { signal } = ctrl;
    const id = encodeURIComponent(caseId);
    const q = `?lang=${lang === "es" ? "es" : "en"}`;
    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      let card: Card;
      try {
        card = await fetchCard(caseId, signal);
      } catch (error) {
        if (!signal.aborted)
          setRun({ ...NONE, status: error instanceof CaseNotFound ? "missing" : "locked" });
        return;
      }
      if (!loadCaseReadToken(caseId)) return setRun({ ...NONE, status: "locked", card });
      const [timeline, listing] = await Promise.all([
        readJson<CaseTimeline>(`/cases/${id}/timeline${q}`, caseId, signal).catch(() => null),
        readJson<RealListing>(`/cases/${id}/real-listing${q}`, caseId, signal).catch(() => null),
      ]);
      if (signal.aborted) return;
      if (!timeline) return setRun({ ...NONE, status: "locked", card });
      setRun({ status: "ready", card, timeline, listing });
      // The agent is still at work: read its timeline (and the card it may update) each second.
      const again = async () => {
        try {
          const next = await readJson<CaseTimeline>(`/cases/${id}/timeline${q}`, caseId, signal);
          if (signal.aborted) return;
          if (next) {
            const fresh = isRunning(next)
              ? card
              : await fetchCard(caseId, signal).catch(() => card);
            card = fresh;
            setRun({ status: "ready", card, timeline: next, listing });
            if (!isRunning(next)) return;
          }
        } catch {
          if (signal.aborted) return;
        }
        timer = setTimeout(again, POLL_MS);
      };
      if (isRunning(timeline)) timer = setTimeout(again, POLL_MS);
    })();
    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [caseId, lang]);
  return run;
}

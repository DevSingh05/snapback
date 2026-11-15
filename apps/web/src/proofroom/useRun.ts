// What the Proof Room reads: the roster (GET /agents, with the bundled copy until it lands),
// and for a case its card, timeline and real-listing read. The timeline needs the case's read
// token, sent in a header and never put in an address. While the agent is still running the
// timeline arrives live through case/useTimelineStream (a stream, else a read each second).
// Reads only.
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
import { openTimelineStream } from "../case/useTimelineStream";
import { asRoster, bundledRoster, type Roster } from "./model";
import { SAMPLE_ID, sampleCard, sampleTimeline } from "./sample";

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
    let stop: (() => void) | undefined;
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
      const listing = await readJson<RealListing>(
        `/cases/${id}/real-listing${q}`,
        caseId,
        signal,
      ).catch(() => null);
      if (signal.aborted) return;
      // The timeline, live: a stream when the server has one, else a read each second, for as
      // long as the agent is running (case/useTimelineStream). It stops by itself when done.
      let wasRunning = false;
      stop = openTimelineStream({
        caseId,
        lang,
        onTimeline: (timeline) => {
          if (signal.aborted) return;
          setRun({ status: "ready", card, timeline, listing });
          // The agent's extra checks can change the result: read the card again once it ends.
          if (wasRunning && timeline.running !== true) {
            fetchCard(caseId, signal)
              .then((fresh) => {
                card = fresh;
                if (!signal.aborted) setRun({ status: "ready", card, timeline, listing });
              })
              .catch(() => {});
          }
          wasRunning = timeline.running === true;
        },
        onFeed: (feed) => {
          if (feed !== "off" || signal.aborted) return;
          // No timeline could be read at all: the steps stay closed; the card still shows.
          setRun((now) => (now.timeline ? now : { ...NONE, status: "locked", card }));
        },
      });
    })();
    return () => {
      ctrl.abort();
      stop?.();
    };
  }, [caseId, lang]);
  return run;
}

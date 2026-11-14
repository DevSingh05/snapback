import { useEffect, useState } from "react";

import { apiBase, apiFetchRead, loadCaseReadToken } from "../api";
import type { TraceEvent } from "../contracts";
import type { EvidenceFile } from "../evidence/types";
import { mergeEvent } from "../trace/parse";
import { openLiveTrace } from "../trace/stream";

export type EvidenceImages = Record<string, { ad?: string | null; scan?: string | null }>;

export interface WalkLive {
  evidence: EvidenceFile | null;
  /** Blob URLs of the ad photo and the scan view it matched, keyed by photo alias. */
  images: EvidenceImages;
  events: TraceEvent[];
}

const NONE: WalkLive = { evidence: null, images: {}, events: [] };

/**
 * A live case's evidence file, its real images and its trace, read from our own API with the
 * case's read token in a header (never in the address). Images arrive as blob URLs and every one
 * is revoked when the case changes or the page closes. Anything that fails is simply absent: the
 * screens then show the drawn stand-in, labelled as one.
 */
export function useWalkLive(caseId: string | null | undefined): WalkLive {
  const [live, setLive] = useState<WalkLive>(NONE);
  useEffect(() => {
    const base = apiBase();
    if (!base || !caseId) return;
    const id = caseId;
    const ctl = new AbortController();
    const blobs: string[] = [];
    const path = `/cases/${encodeURIComponent(id)}/evidence`;

    async function image(alias: string, kind: "photo" | "scan"): Promise<string | null> {
      try {
        const pending = apiFetchRead(`${path}/${encodeURIComponent(alias)}/${kind}.jpg`, id, {
          signal: ctl.signal,
        });
        const res = pending ? await pending : null;
        if (!res || !res.ok || ctl.signal.aborted) return null;
        const url = URL.createObjectURL(await res.blob());
        blobs.push(url);
        return url;
      } catch {
        return null;
      }
    }

    async function load() {
      try {
        const pending = apiFetchRead(path, id, { signal: ctl.signal });
        const res = pending ? await pending : null;
        if (!res || !res.ok) return;
        const evidence = (await res.json()) as EvidenceFile;
        if (ctl.signal.aborted) return;
        setLive((l) => ({ ...l, evidence }));
        for (const p of evidence.photos) {
          const [ad, scan] = await Promise.all([image(p.alias, "photo"), image(p.alias, "scan")]);
          if (ctl.signal.aborted) return;
          setLive((l) => ({ ...l, images: { ...l.images, [p.alias]: { ad, scan } } }));
        }
      } catch {
        // No evidence yet: the walk still works, with nothing to open in the drawer.
      }
    }
    void load();
    const closeTrace = openLiveTrace(
      base,
      id,
      (e) => !ctl.signal.aborted && setLive((l) => ({ ...l, events: mergeEvent(l.events, e) })),
      () => {},
      loadCaseReadToken(id),
    );
    return () => {
      ctl.abort();
      closeTrace();
      for (const u of blobs) URL.revokeObjectURL(u);
      setLive(NONE);
    };
  }, [caseId]);
  return live;
}

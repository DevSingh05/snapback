import { useEffect, useState } from "react";

import { apiBase, apiFetchRead, loadCaseReadToken } from "../api";
import type { AerialProofResponse, AerialSideOut, DataSource } from "../contracts";
import type { AerialSide } from "./AerialProof";

export type LiveAerial =
  | { status: "loading" }
  | { status: "error" }
  | {
      status: "ready";
      source: DataSource;
      claimed: AerialSide;
      /** Null when no photo was located elsewhere: only the claimed building is shown. */
      matched: AerialSide | null;
    };

/** True when a live read is possible: an API is configured and this browser holds the read token. */
export function canGoLive(caseId: string | undefined): caseId is string {
  return Boolean(caseId && apiBase() && loadCaseReadToken(caseId));
}

// Our own route only; an image address from the API is never fetched if it points elsewhere.
const ownImage = (caseId: string): RegExp => {
  const id = encodeURIComponent(caseId).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^/cases/${id}/aerial/(claimed|matched)\\.jpg(\\?[^#]*)?$`);
};

/**
 * Fetches the aerial proof with the read token in a header, then each live tile's bytes the same
 * way, and hands them over as blob URLs. Every blob URL is revoked when the case changes or the
 * component unmounts. A tile that is null, or whose image answers anything but 200, comes back
 * with no imageUrl, which the view shows as "not available" (never a broken image).
 */
export function useLiveAerial(caseId: string | undefined, enabled: boolean): LiveAerial {
  const [state, setState] = useState<{ key: string; value: LiveAerial } | null>(null);
  const key = caseId ?? "";

  useEffect(() => {
    if (!enabled || !caseId) return;
    const id = caseId;
    const ctl = new AbortController();
    const blobs: string[] = [];
    const own = ownImage(id);

    async function image(side: AerialSideOut | null): Promise<string | undefined> {
      const path = side?.image_url;
      if (!side?.tile || side.tile.source !== "live" || !path || !own.test(path)) {
        return undefined;
      }
      try {
        const pending = apiFetchRead(path, id, { signal: ctl.signal });
        const res = pending ? await pending : null;
        if (!res || !res.ok || ctl.signal.aborted) return undefined;
        const blob = await res.blob();
        if (ctl.signal.aborted) return undefined;
        const url = URL.createObjectURL(blob);
        blobs.push(url);
        return url;
      } catch {
        return undefined;
      }
    }

    async function load() {
      try {
        const pending = apiFetchRead(`/cases/${encodeURIComponent(id)}/aerial`, id, {
          signal: ctl.signal,
        });
        const res = pending ? await pending : null;
        if (!res || !res.ok) throw new Error("aerial");
        const body = (await res.json()) as AerialProofResponse;
        const [c, m] = await Promise.all([image(body.claimed), image(body.matched)]);
        if (ctl.signal.aborted) return;
        const side = (s: AerialSideOut, imageUrl?: string): AerialSide => ({
          tile: s.tile,
          record: s.record,
          imageUrl,
        });
        setState({
          key,
          value: {
            status: "ready",
            source: body.source,
            claimed: side(body.claimed, c),
            matched: body.matched ? side(body.matched, m) : null,
          },
        });
      } catch {
        if (!ctl.signal.aborted) setState({ key, value: { status: "error" } });
      }
    }
    void load();

    return () => {
      ctl.abort();
      for (const u of blobs) URL.revokeObjectURL(u);
    };
  }, [caseId, enabled, key]);

  return state && state.key === key ? state.value : { status: "loading" };
}

import { useEffect, useState } from "react";

import { apiFetchRead } from "../api";

const ALIAS = /^[A-Z]\d{1,3}$/;

/**
 * The ad's own photo for a case, fetched with the read token in a header (never in an address)
 * and shown through a blob URL, revoked on change or unmount. Null until it loads, and null when
 * there is no case, no token, no such photo or the answer is not an image: the caller then shows
 * its labelled placeholder. Reuses `GET /cases/{id}/evidence/{alias}/photo.jpg`.
 */
export function useAdPhoto(caseId: string | null | undefined, alias: string | null | undefined) {
  const [state, setState] = useState<{ key: string; url: string | null } | null>(null);
  const key = `${caseId ?? ""}/${alias ?? ""}`;

  useEffect(() => {
    if (!caseId || !alias || !ALIAS.test(alias)) return;
    const ctl = new AbortController();
    let blob: string | null = null;
    const path = `/cases/${encodeURIComponent(caseId)}/evidence/${alias}/photo.jpg`;
    const pending = apiFetchRead(path, caseId, { signal: ctl.signal });
    if (!pending) return;
    pending
      .then(async (res) => {
        if (!res.ok || !(res.headers.get("content-type") ?? "").startsWith("image/")) return;
        const body = await res.blob();
        if (ctl.signal.aborted) return;
        blob = URL.createObjectURL(body);
        setState({ key, url: blob });
      })
      .catch(() => {});
    return () => {
      ctl.abort();
      if (blob) URL.revokeObjectURL(blob);
    };
  }, [caseId, alias, key]);

  return state && state.key === key ? state.url : null;
}

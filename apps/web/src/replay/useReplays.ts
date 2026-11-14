import { useEffect, useState } from "react";

import { apiFetch, dataMode } from "../api";
import { bundledReplays } from "./index";
import type { Replay } from "./types";

function usable(list: unknown): list is Replay[] {
  return (
    Array.isArray(list) &&
    list.length > 0 &&
    list.every((r) => r && typeof r.slug === "string" && Array.isArray(r.steps) && r.snapback)
  );
}

// The replays to show. They start as the bundled copy of demo/replays so the page never waits;
// when the API is connected, GET /replays replaces them (same files, served read-only).
export function useReplays(): Replay[] {
  const [list, setList] = useState<Replay[]>(bundledReplays);
  useEffect(() => {
    if (dataMode() === "fixture") return;
    let live = true;
    apiFetch("/replays")
      .then((res) => (res.ok ? res.json() : null))
      .then((body: unknown) => {
        if (live && usable(body)) setList(body);
      })
      .catch(() => {
        // the bundled copy stays
      });
    return () => {
      live = false;
    };
  }, []);
  return list;
}

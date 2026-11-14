import type { FindingStatus, Replay, ReplayVerdict } from "./types";

// Every replay file is read from demo/replays (the one source of truth the API also serves) and,
// for the web's own test fixtures, ./fixtures. Nothing here names a slug: add a file, get a page.
const files = import.meta.glob<Replay>(["../../../../demo/replays/*.json", "./fixtures/*.json"], {
  eager: true,
  import: "default",
});

export function bundledReplays(): Replay[] {
  const bySlug = new Map<string, Replay>();
  for (const replay of Object.values(files)) {
    if (!bySlug.has(replay.slug)) bySlug.set(replay.slug, replay);
  }
  return [...bySlug.values()].sort((a, b) => a.slug.localeCompare(b.slug));
}

export function getReplay(slug: string, from: Replay[] = bundledReplays()): Replay | undefined {
  return from.find((r) => r.slug === slug);
}

export function replayForCase(
  caseId: string,
  from: Replay[] = bundledReplays(),
): Replay | undefined {
  return from.find((r) => r.case_id === caseId);
}

// The replay the header tab opens. If this file is not there the tab opens the index instead.
export const FEATURED_REPLAY_SLUG = "owner-not-poster-door-code";

// Locked card words (decisions.md, 2026-11-13 22:40). The verdict state picks the words in code.
export const REPLAY_VERDICT_WORDS: Record<ReplayVerdict, string> = {
  dont_pay: "Don't pay. Something here doesn't match.",
  hold: "Hold off for now",
};

export type { Replay } from "./types";

export const FINDING_WORDS: Record<FindingStatus, string> = {
  matches: "Matches",
  doesnt_match: "Doesn't match",
  not_confirmed: "Not confirmed",
  warning: "Warning",
  not_checked: "Not checked",
  // A risky ask. The card words it "Warning" on the price row, which is where replays put it.
  red_flag: "Warning",
};

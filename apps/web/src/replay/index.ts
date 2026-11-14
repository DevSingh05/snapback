import type { FindingStatus, Replay, ReplayStepKind, ReplayVerdict } from "./types";

// Every replay file is read from demo/replays (the one source of truth the API also serves).
// Nothing here names a slug: add a file, get a page. Test fixtures are never bundled; a test
// adds its own with registerTestReplays.
const files = import.meta.glob<Replay>("../../../../demo/replays/*.json", {
  eager: true,
  import: "default",
});

const testOnly: Replay[] = [];

export function registerTestReplays(list: Replay[]): void {
  testOnly.push(...list);
}

export function bundledReplays(): Replay[] {
  const bySlug = new Map<string, Replay>();
  for (const replay of [...Object.values(files), ...testOnly]) {
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

export const FINDING_WORDS: Record<Exclude<FindingStatus, "red_flag">, string> = {
  matches: "Matches",
  doesnt_match: "Doesn't match",
  not_confirmed: "Not confirmed",
  warning: "Warning",
  not_checked: "Not checked",
};

// A red flag on a risky ask (a hold request or the payment) is worded "Warning", as the card
// does on its price row; on any other step it is "Doesn't match".
export function findingWord(status: FindingStatus, stepKind: ReplayStepKind): string {
  if (status !== "red_flag") return FINDING_WORDS[status];
  return stepKind === "hold_request" || stepKind === "payment" ? "Warning" : "Doesn't match";
}

// Card text that already opens with its own tone word. The page adds no second one.
const OWN_TONE = /^(matches|doesn't match|not confirmed|warning|not checked|not shown)\b/i;
export function startsWithToneWord(text: string): boolean {
  return OWN_TONE.test(text.trim());
}

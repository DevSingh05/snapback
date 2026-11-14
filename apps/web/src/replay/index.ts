import zelleCopiedTour from "./fixtures/zelle-deposit-copied-tour.json";
import type { FindingStatus, Replay, ReplayVerdict } from "./types";

// Fixtures only until D8 (#71) lands demo/replays/*.json; then this list reads those files.
const REPLAYS: Replay[] = [zelleCopiedTour as Replay];

export function getReplay(slug: string): Replay | undefined {
  return REPLAYS.find((r) => r.slug === slug);
}

export function replayForCase(caseId: string): Replay | undefined {
  return REPLAYS.find((r) => r.case_id === caseId);
}

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
};

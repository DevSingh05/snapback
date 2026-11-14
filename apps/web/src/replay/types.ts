// Proposed shape of demo/replays/<slug>.json (D8, issue #71). The web app reads exactly this.
// Deliberately has no field for a victim name or an address: a replay cannot carry either.

export type ReplayStepKind = "listing" | "chat" | "hold_request" | "payment" | "discovery";

// The two verdict states a replay may stop at. Card words come from code (REPLAY_VERDICT_WORDS),
// never from the JSON, so the locked wording cannot drift.
// Locked row words (decisions.md 22:40).
export type FindingStatus =
  "matches" | "doesnt_match" | "not_confirmed" | "warning" | "not_checked" | "red_flag";

export type ReplayVerdict = "dont_pay" | "hold";

export interface ReplayStep {
  id: string;
  kind: ReplayStepKind;
  /** Date as reported by the source, YYYY-MM-DD; empty when the source gives none for the step. */
  reported_on: string;
  /** Short title, plain words. */
  label: string;
  /** One or two sentences of what happened, paraphrased, no names. */
  detail: string;
}

export interface Replay {
  slug: string;
  /** The SNAPBACK case this replay opens from (the card page links here). */
  case_id: string;
  title: string;
  /** Which proof carries the case. */
  pattern: "place" | "person" | "price";
  /** True for a team-made example modelled on a public pattern, not on one named report. */
  fictional: boolean;
  /** Required when fictional is false. A fictional replay carries no source and no date. */
  source?: { name: string; url: string; published_on: string };
  /** Amount in dollars as reported by the source, rounded as reported. */
  amount_usd: number;
  /** Steps in the order they happened. Exactly one has kind "payment". */
  steps: ReplayStep[];
  snapback: {
    verdict: ReplayVerdict;
    /** Optional cross-check: id of the payment step. The stop is always the first payment step. */
    stop_before?: string;
    /** What SNAPBACK's run found at each step it saw, in the locked row words. */
    findings: { step_id: string; status: FindingStatus; text: string }[];
  };
  /** What SNAPBACK cannot catch in this case, in plain words. */
  cant_catch?: string;
}

import type { DataSource } from "../contracts";

export type UploadState =
  | { step: "input" }
  | { step: "reading" }
  | { step: "checking"; caseId: string; challengeText: string; source: DataSource }
  | { step: "approval"; caseId: string; challengeText: string; source: DataSource }
  | { step: "waiting"; caseId: string; challengeText: string; source: DataSource }
  | { step: "done"; caseId: string; challengeSent: boolean; source: DataSource }
  | { step: "error"; message: string };

export type UploadEvent =
  | { type: "submit" }
  | { type: "created"; caseId: string; challengeText: string | null; source: DataSource }
  | { type: "checked" }
  | { type: "approve" }
  | { type: "skip" }
  | { type: "done" }
  | { type: "fail"; message: string }
  | { type: "retry" };

export const initialState: UploadState = { step: "input" };

// The renter-approval gate: "waiting" (the live-check message is out) is reachable only from
// "approval" through an explicit approve event. Unknown events for a step return the same state.
export function reduce(state: UploadState, event: UploadEvent): UploadState {
  switch (event.type) {
    case "submit":
      return state.step === "input" ? { step: "reading" } : state;
    case "created":
      if (state.step !== "reading") return state;
      // No challenge drafted (out-of-scope listing): there is nothing to approve, so go to the card.
      if (event.challengeText === null) {
        return { step: "done", caseId: event.caseId, challengeSent: false, source: event.source };
      }
      return {
        step: "checking",
        caseId: event.caseId,
        challengeText: event.challengeText,
        source: event.source,
      };
    case "checked":
      return state.step === "checking" ? { ...state, step: "approval" } : state;
    case "approve":
      return state.step === "approval" ? { ...state, step: "waiting" } : state;
    case "skip":
      return state.step === "approval"
        ? { step: "done", caseId: state.caseId, challengeSent: false, source: state.source }
        : state;
    case "done":
      return state.step === "waiting"
        ? { step: "done", caseId: state.caseId, challengeSent: true, source: state.source }
        : state;
    case "fail":
      return ["reading", "checking", "approval", "waiting"].includes(state.step)
        ? { step: "error", message: event.message }
        : state;
    case "retry":
      return state.step === "error" ? initialState : state;
  }
}

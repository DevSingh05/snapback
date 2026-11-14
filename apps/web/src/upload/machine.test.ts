import { describe, expect, it } from "vitest";

import { initialState, reduce, type UploadEvent, type UploadState } from "./machine";

const created = {
  caseId: "7Q2M",
  challengeText: "Please send a photo.",
  source: "fixture" as const,
};

function run(events: UploadEvent[]): UploadState {
  return events.reduce(reduce, initialState);
}

describe("upload state machine", () => {
  it("starts on input", () => {
    expect(initialState.step).toBe("input");
  });

  it("goes input -> reading on submit and -> checking when the case exists", () => {
    expect(run([{ type: "submit" }]).step).toBe("reading");
    expect(run([{ type: "submit" }, { type: "created", ...created }]).step).toBe("checking");
  });

  it("goes checking -> approval and keeps the message for the renter", () => {
    const s = run([{ type: "submit" }, { type: "created", ...created }, { type: "checked" }]);
    expect(s.step).toBe("approval");
    expect(s.step === "approval" && s.challengeText).toBe("Please send a photo.");
  });

  it("approval gate: waiting is unreachable without an approve event", () => {
    const s = run([
      { type: "submit" },
      { type: "created", ...created },
      { type: "checked" },
      { type: "done" },
    ]);
    expect(s.step).toBe("approval");
  });

  it("approve moves approval -> waiting, then done with the challenge marked sent", () => {
    const s = run([
      { type: "submit" },
      { type: "created", ...created },
      { type: "checked" },
      { type: "approve" },
    ]);
    expect(s.step).toBe("waiting");
    const d = reduce(s, { type: "done" });
    expect(d).toMatchObject({ step: "done", caseId: "7Q2M", challengeSent: true });
  });

  it("skip leaves approval for done with no challenge sent", () => {
    const s = run([
      { type: "submit" },
      { type: "created", ...created },
      { type: "checked" },
      { type: "skip" },
    ]);
    expect(s).toMatchObject({ step: "done", challengeSent: false });
  });

  it("a failed request lands on error and retry returns to input", () => {
    const s = run([{ type: "submit" }, { type: "fail", message: "Server down" }]);
    expect(s).toMatchObject({ step: "error", message: "Server down" });
    expect(reduce(s, { type: "retry" }).step).toBe("input");
  });

  it("ignores events that do not fit the current step", () => {
    expect(reduce(initialState, { type: "approve" })).toBe(initialState);
    expect(reduce(initialState, { type: "created", ...created })).toBe(initialState);
  });
});

describe("no challenge drafted", () => {
  it("skips the approval and goes straight to done", () => {
    const s = reduce(
      { step: "reading" },
      { type: "created", caseId: "9ZZZ", challengeText: null, source: "live" },
    );
    expect(s).toEqual({ step: "done", caseId: "9ZZZ", challengeSent: false, source: "live" });
  });

  it("a server refusal during approval lands on the error step", () => {
    const approval = { step: "approval", caseId: "A", challengeText: "t", source: "live" } as const;
    expect(reduce(approval, { type: "fail", message: "no" }).step).toBe("error");
  });
});

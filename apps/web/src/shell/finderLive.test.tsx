import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FinderProposal, FinderReply, FinderState } from "../contracts";
import { FinderPage } from "./FinderPage";
import { learnedLines, loadAuth } from "./finderApi";
import { loadFinderEvents, recordFinderEvent } from "./finderStore";

// A scripted Finder service: the page talks to it as it would to src/snapback/api/finder.py.
const TOKEN = "tok-secret-1";
const PROPOSAL: FinderProposal = {
  id: "pr-1",
  key: "propose_no_walkup",
  update: { no_walkup: true },
  text: "Skip walk-ups from now on?",
  evidence: "you passed on 2 of 2 walk-ups",
  reason: "Two of two.",
  chosen_by: "model",
  status: "proposed",
  at: "2026-11-14T20:00:00Z",
};
const PICK = {
  pid: "fx-fnd-03",
  rank: 1,
  kind: "apartment" as const,
  has_scan: true,
  line: "Apartment, 2 floor plans, from $1,180 a month, a 3D scan on record, as of CoStar's last research",
  why: "It fits the budget and has a 3D scan.",
  chosen_by: "model" as const,
  as_of: "as of CoStar's last research",
  rent_from: 1180,
  walkup: true,
  parking: false,
};

function baseState(): FinderState {
  return {
    session_id: "fs-1",
    source: "fixture",
    mode: "deepagents",
    applied: {
      no_walkup: false,
      needs_parking: false,
      max_rent: null,
      avoid_property_ids: [],
      prefer_scans: false,
    },
    proposals: [],
    picks: [],
    learned: { budget_set: false },
    notes: [],
    trace: [],
    as_of: "as of CoStar's last research",
  };
}

interface Call {
  url: string;
  method: string;
  auth: string | null;
  body: unknown;
}

function service() {
  let state = baseState();
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : null;
    calls.push({ url, method: init?.method ?? "GET", auth: headers.get("Authorization"), body });
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.endsWith("/finder/sessions"))
      return json({ session_id: "fs-1", token: TOKEN, source: "fixture", mode: "deepagents" }, 201);
    if (url.endsWith("/state")) return json(state);
    if (url.endsWith("/message")) {
      state = {
        ...state,
        proposals: [PROPOSAL],
        picks: [PICK],
        learned: { budget_set: true, passed_walkups: "2 of 2" },
        trace: [
          {
            session_id: "fs-1",
            seq: 1,
            at: "2026-11-14T20:00:00Z",
            kind: "todo",
            options: ["[x] Offer what to remember", "[ ] Lead the list"],
            pick: null,
            reason: "Plan: 1 of 2 steps done.",
            source: "fixture",
            chosen_by: "model",
          },
          {
            session_id: "fs-1",
            seq: 2,
            at: "2026-11-14T20:00:01Z",
            kind: "agent",
            options: [],
            pick: "sub-agent: preferences",
            reason: "Handed to the preferences sub-agent.",
            source: "fixture",
            chosen_by: "model",
          },
        ],
      };
      const reply: FinderReply = {
        session_id: "fs-1",
        source: "fixture",
        mode: "deepagents",
        reply: "You seem to skip walk-ups; want me to remember that?",
        reply_by: "model",
        proposals: [PROPOSAL],
        picks: [PICK],
        as_of: "as of CoStar's last research",
      };
      return json(reply);
    }
    if (url.includes("/proposals/")) {
      const accepted = { ...PROPOSAL, status: "accepted" as const };
      state = {
        ...state,
        proposals: [accepted],
        applied: { ...state.applied, no_walkup: true },
      };
      return json(accepted);
    }
    return json({ detail: "no" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.stubEnv("VITE_API_URL", "/api");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("Finder, connected to the deep agent", () => {
  it("starts a session, keeps its token in sessionStorage and only ever sends it in a header", async () => {
    const { calls } = service();
    render(<FinderPage />);
    await screen.findByTestId("finder-status");
    expect(loadAuth()).toEqual({ sid: "fs-1", token: TOKEN });
    expect(window.location.href).not.toContain(TOKEN);
    expect(calls.every((c) => !c.url.includes(TOKEN))).toBe(true);
    const state = calls.find((c) => c.url.endsWith("/state"))!;
    expect(state.auth).toBe(`Bearer ${TOKEN}`);
    expect(screen.getByTestId("finder-status")).toHaveTextContent("Claude reads what you say");
  });

  it("replies with a stamp, offers a proposal that applies only on Yes, and shows the picks", async () => {
    const { calls } = service();
    render(<FinderPage />);
    await screen.findByTestId("finder-status");
    fireEvent.change(screen.getByLabelText("Your message"), {
      target: { value: "under $1,500, no walk-ups" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByTestId("finder-working")).toBeInTheDocument();
    const reply = await screen.findByTestId("finder-reply");
    expect(reply).toHaveTextContent("Picked by the model");
    expect(reply).toHaveTextContent("You seem to skip walk-ups");
    const sent = calls.find((c) => c.url.endsWith("/message"))!;
    expect(sent.body).toMatchObject({ text: "under $1,500, no walk-ups" });

    const card = await screen.findByTestId("finder-proposal");
    expect(card).toHaveTextContent("Skip walk-ups from now on?");
    expect(card).toHaveTextContent("Because you passed on 2 of 2 walk-ups.");
    expect(screen.queryByTestId("learned-chip")).toBeNull(); // nothing kept before Yes
    expect(screen.getAllByTestId("learned-line").map((l) => l.textContent)).toEqual([
      "Passed on 2 of 2 walk-ups",
      "You set a budget",
    ]);
    const pick = screen.getByTestId("finder-pick");
    expect(pick).toHaveTextContent("from $1,180 a month");
    expect(pick).toHaveTextContent("It fits the budget and has a 3D scan.");
    expect(pick).toHaveTextContent("Walk-up");
    expect(within(pick).getByTestId("pick-sample")).toBeInTheDocument(); // fixture: no fake link
    expect(screen.getByTestId("finder-how")).toHaveTextContent(
      "Handed to the preferences sub-agent.",
    );

    fireEvent.click(within(card).getByRole("button", { name: "Yes" }));
    await waitFor(() =>
      expect(screen.getByTestId("learned-chip")).toHaveTextContent("No walk-ups"),
    );
    expect(screen.queryByTestId("finder-proposal")).toBeNull();
    const decided = calls.find((c) => c.url.includes("/proposals/pr-1"))!;
    expect(decided.body).toEqual({ decision: "accept" });
    expect(screen.queryByRole("button", { name: /Forget/ })).toBeNull(); // the API cannot forget
  });

  it("sends what you did on the map as signals, once, as soon as the tab opens", async () => {
    const signal = {
      kind: "pass" as const,
      place_kind: "apartment" as const,
      has_scan: false,
      rent_from: 1500,
      walkup: true,
      parking: false,
    };
    recordFinderEvent("passed", "Passed on a place", signal);
    recordFinderEvent("passed", "Passed on a place", signal);
    const { calls } = service();
    render(<FinderPage />);
    await screen.findByTestId("finder-reply");
    const sent = calls.filter((c) => c.url.endsWith("/message"));
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({ signals: [signal, signal] });
    expect(loadFinderEvents().every((e) => e.sent)).toBe(true);
    expect(screen.getAllByTestId("finder-did")).toHaveLength(2);
  });

  it("a pass on a pick goes back as a signal with the record's facts, never the place id", async () => {
    const { calls } = service();
    render(<FinderPage />);
    await screen.findByTestId("finder-status");
    fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const pick = await screen.findByTestId("finder-pick");
    await waitFor(() =>
      expect(within(pick).getByRole("button", { name: "Not for me" })).not.toBeDisabled(),
    );
    fireEvent.click(within(pick).getByRole("button", { name: "Not for me" }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/message"))).toHaveLength(2));
    const body = calls.filter((c) => c.url.endsWith("/message"))[1]!.body;
    expect(body).toEqual({
      signals: [
        {
          kind: "pass",
          place_kind: "apartment",
          has_scan: true,
          rent_from: 1180,
          walkup: true,
          parking: false,
        },
      ],
    });
    expect(JSON.stringify(body)).not.toContain("fx-fnd");
  });

  it("falls back to the rules on this device, honestly, when the service is down", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("bad gateway", { status: 502 })),
    );
    render(<FinderPage />);
    const honest = await screen.findByTestId("finder-honest");
    expect(honest).toHaveTextContent("The Finder service is not running right now");
    expect(honest).toHaveTextContent("Picked by our rules");
    expect(within(honest).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("a turn still running (409) reads as still thinking; a 429 says the daily limit", async () => {
    let status = 409;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const json = (d: unknown, s = 200) => new Response(JSON.stringify(d), { status: s });
        if (url.endsWith("/finder/sessions"))
          return json({ session_id: "fs-1", token: TOKEN, source: "fixture", mode: "policy" }, 201);
        if (url.endsWith("/state")) return json(baseState());
        return json({ detail: "busy or capped" }, status);
      }),
    );
    render(<FinderPage />);
    await screen.findByTestId("finder-status");
    const send = (words: string) => {
      fireEvent.change(screen.getByLabelText("Your message"), { target: { value: words } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    };
    send("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent("Still thinking");
    status = 429;
    send("hello again");
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Daily limit reached; your saved preferences still filter places.",
      ),
    );
  });

  it("puts what it learned in plain words", () => {
    expect(
      learnedLines({
        passed_walkups: "3 of 3",
        passed_no_parking: "2 of 3",
        picked_with_scan: "2 of 2",
        picked_below_budget: "2 of 2",
        budget_set: true,
        unknown_key: "x",
      }),
    ).toEqual([
      "Passed on 3 of 3 walk-ups",
      "Passed on 2 of 3 places without parking",
      "Picked 2 of 2 places with a 3D scan",
      "2 of 2 picks cost well under your budget",
      "You set a budget",
    ]);
  });
});

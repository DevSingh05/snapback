import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { saveCaseReadToken } from "../api";
import type { Card } from "../contracts";
import type { CreateCase } from "../upload/api";
import { OneBox, VerdictCard } from "./OneBox";

// A mocked API with the route shapes the one box calls in live mode.
interface Call {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
}

const READ = "tok_read_789";
const state = {
  session_id: "fs-1",
  source: "live",
  mode: "policy",
  applied: {},
  proposals: [
    {
      id: "p1",
      key: "propose_no_walkup",
      update: {},
      text: "Skip walk-ups from now on?",
      evidence: "you passed on two walk-ups",
      reason: "",
      chosen_by: "policy",
      status: "proposed",
      at: "2026-11-14T12:00:00Z",
    },
  ],
  picks: [],
  learned: {},
  notes: [],
  trace: [],
};

function server(evidence: { alias: string; status: string }[] = []) {
  const calls: Call[] = [];
  const json = (body: unknown, code = 200) =>
    new Response(JSON.stringify(body), {
      status: code,
      headers: { "Content-Type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      calls.push({ method, path, headers: new Headers(init?.headers), body: init?.body });
      if (path === "/api/healthz") return json({ status: "ok", data_source: "live" });
      if (path === "/api/voice/status") return json({ tts: false, stt: false });
      if (path === "/api/finder/sessions") return json({ session_id: "fs-1", token: "ft" }, 201);
      if (path === "/api/finder/fs-1/state") return json(state);
      if (path === "/api/finder/fs-1/message")
        return json({
          session_id: "fs-1",
          source: "live",
          mode: "policy",
          reply: "Here is what fits.",
          reply_by: "policy",
          proposals: state.proposals,
          picks: [],
          as_of: "",
        });
      if (path === "/api/cases/7Q2M/card") return json({ ...(cardHold as Card), source: "live" });
      if (path === "/api/cases/7Q2M/evidence")
        return json({ case_id: "7Q2M", source: "live", photos: evidence });
      if (/\/api\/cases\/7Q2M\/evidence\/\w+\/scan\.jpg$/.test(path))
        return new Response(new TextEncoder().encode("jpg"), {
          status: 200,
          headers: { "Content-Type": "image/jpeg" },
        });
      return json({ detail: "nope" }, 404);
    }),
  );
  return calls;
}

const box = () => screen.getByLabelText(/paste an ad, a link, or say what you need/i);
async function paste(user: ReturnType<typeof userEvent.setup>, words: string) {
  await user.click(box());
  await user.paste(words);
  await user.click(screen.getByRole("button", { name: /^send$/i }));
}

const AD =
  "2 bed 2 bath, $1,350/month, utilities included. I'm abroad so I can't show it; send the $600 deposit by Zelle.";

beforeEach(() => {
  vi.stubEnv("VITE_API_URL", "/api");
  window.sessionStorage.clear();
  window.localStorage.clear();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("the walk card reads the real scan view at run time", () => {
  it("takes the photo located in the claimed home, with the read token, and frees it after", async () => {
    const calls = server([
      { alias: "P1", status: "located_elsewhere" },
      { alias: "P2", status: "located_in_claimed" },
    ]);
    const create = vi.fn(() => "blob:scan-p2");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    saveCaseReadToken("7Q2M", READ);
    const { unmount } = render(<VerdictCard caseId="7Q2M" source="live" />);
    const walk = await screen.findByTestId("ob-walk");
    await waitFor(() =>
      expect(within(walk).getByRole("img")).toHaveAttribute("src", "blob:scan-p2"),
    );
    expect(walk).toHaveTextContent("From the 3D scan");
    expect(within(walk).queryByTestId("sample-photo")).not.toBeInTheDocument();
    const scans = calls.filter((c) => c.path.endsWith("/scan.jpg"));
    expect(scans.map((c) => c.path)).toEqual(["/api/cases/7Q2M/evidence/P2/scan.jpg"]);
    expect(scans[0]!.headers.get("Authorization")).toBe(`Bearer ${READ}`);
    const ev = calls.find((c) => c.path === "/api/cases/7Q2M/evidence")!;
    expect(ev.headers.get("Authorization")).toBe(`Bearer ${READ}`);
    expect(calls.some((c) => c.path.includes(READ))).toBe(false);
    unmount();
    expect(revoke).toHaveBeenCalledWith("blob:scan-p2");
  });

  it("with no photo placed in the claimed home it keeps the stamped sample", async () => {
    const calls = server([
      { alias: "P1", status: "located_elsewhere" },
      { alias: "P2", status: "not_located" },
    ]);
    saveCaseReadToken("7Q2M", READ);
    render(<VerdictCard caseId="7Q2M" source="live" />);
    const walk = await screen.findByTestId("ob-walk");
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/cases/7Q2M/evidence")).toBe(true),
    );
    expect(within(walk).getByTestId("sample-photo")).toHaveTextContent("Sample photo");
    expect(calls.some((c) => c.path.endsWith("/scan.jpg"))).toBe(false);
  });
});

describe("a Facebook address never leaves the browser", () => {
  it("a question about a Facebook link asks for the text and calls nothing", async () => {
    const calls = server();
    const user = userEvent.setup();
    render(<OneBox mode="live" />);
    await paste(user, "is facebook.com/marketplace/item/1 legit?");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking a Facebook ad");
    expect(await screen.findByText(/behind a login/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/api/finder") || c.path === "/api/cases")).toBe(
      false,
    );
  });

  it("switching a Facebook ad to the Finder sends the words without the address", async () => {
    const calls = server();
    const user = userEvent.setup();
    const createCase: CreateCase = vi.fn(async () => ({
      case_id: "7Q2M",
      source: "live" as const,
      challenge_text: null,
    }));
    render(<OneBox mode="live" createCase={createCase} />);
    await paste(user, `facebook.com/marketplace/item/123 ${AD}`);
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    await waitFor(() =>
      expect(createCase).toHaveBeenCalledWith(expect.objectContaining({ link: null, text: AD })),
    );
    await user.click(screen.getByTestId("ob-switch"));
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/finder/fs-1/message")).toBe(true),
    );
    const sent = calls
      .filter((c) => c.path === "/api/finder/fs-1/message")
      .map((c) => String(c.body));
    expect(sent.join(" ")).not.toMatch(/facebook/i);
    // The offer it made carries the data chip.
    const offer = await screen.findByTestId("ob-offer");
    expect(within(offer).getByTestId("source-chip")).toHaveTextContent("LIVE");
  });
});

describe("chips on every sample", () => {
  it("the Home tile's sample verdict says FIXTURE even when the page is LIVE", async () => {
    server();
    render(<OneBox mode="live" />);
    // The page's own chip follows the API: LIVE.
    await waitFor(() =>
      expect(
        screen.getAllByTestId("source-chip").some((c) => /LIVE/.test(c.textContent ?? "")),
      ).toBe(true),
    );
    const tile = screen.getByRole("button", { name: /check an ad/i });
    expect(within(tile).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("the Find tile sends the budget its picture shows", async () => {
    server();
    const user = userEvent.setup();
    render(<OneBox mode="live" />);
    await user.click(screen.getByRole("button", { name: /find a place/i }));
    expect(screen.getByTestId("ob-you")).toHaveTextContent(
      "Find me a 1 bed under $1,500 near downtown",
    );
    expect(screen.queryByText("What's your max rent a month?")).not.toBeInTheDocument();
  });
});

describe("the places card claims only FIXTURE until the server answers", () => {
  function searchServer(search: "pending" | "fail") {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL | Request) => {
        const path = String(url);
        if (path === "/api/healthz")
          return new Response(JSON.stringify({ status: "ok", data_source: "live" }));
        if (path === "/api/search")
          return search === "pending"
            ? new Promise<Response>(() => {})
            : new Response(JSON.stringify({ detail: "down" }), { status: 500 });
        // No Finder on this server: code lists the places itself.
        return new Response(JSON.stringify({ detail: "nope" }), { status: 404 });
      }),
    );
  }

  it("while the places are loading", async () => {
    searchServer("pending");
    const user = userEvent.setup();
    render(<OneBox mode="live" />);
    await paste(user, "find me a 1 bed under 1500");
    const places = await screen.findByTestId("ob-places");
    expect(places).toHaveTextContent("Looking up researched places");
    expect(within(places).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("when the places fail to load", async () => {
    searchServer("fail");
    const user = userEvent.setup();
    render(<OneBox mode="live" />);
    await paste(user, "find me a 1 bed under 1500");
    const places = await screen.findByTestId("ob-places");
    await waitFor(() => expect(places).toHaveTextContent("Places did not load"));
    expect(within(places).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });
});

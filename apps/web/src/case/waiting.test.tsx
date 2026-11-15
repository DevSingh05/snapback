// A 202 from a report read means the check is still running: the section says "Still checking…",
// the read is asked again, and the section lands. Never an empty section and never an error.
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { READY_WAIT_MS, apiFetchReadWhenReady, saveCaseReadToken } from "../api";
import type { Card } from "../contracts";
import { CardPage } from "../pages/CardPage";
import { sampleAlert, sampleListing, samplePack } from "./samples";

const live: Card = { ...(cardHold as Card), source: "live", state: "dont_pay" };
const WAITING = { status: "running", retry_after_ms: 500 };

type Reply = { code: number; body: unknown };

/** A server whose routes answer from a queue: the last reply repeats. */
function server(routes: Record<string, Reply[]>) {
  const calls: string[] = [];
  vi.stubEnv("VITE_API_URL", "/api");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL | Request) => {
      const path = String(url);
      calls.push(path);
      const key = Object.keys(routes).find((k) => path.split("?")[0]!.endsWith(k));
      const queue = key ? routes[key]! : [{ code: 404, body: { detail: "none" } }];
      const reply = queue.length > 1 ? queue.shift()! : queue[0]!;
      return new Response(JSON.stringify(reply.body), {
        status: reply.code,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("report reads that answer 202", () => {
  it("shows Still checking per section, then the sections, with no error state", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    server({
      "/cases/7Q2M/card": [{ code: 200, body: live }],
      "/evidence": [
        { code: 202, body: WAITING },
        { code: 404, body: { detail: "none" } },
      ],
      "/real-listing": [
        { code: 202, body: WAITING },
        { code: 200, body: sampleListing({ source: "live" }) },
      ],
      "/copy-alert": [
        { code: 202, body: WAITING },
        { code: 200, body: sampleAlert({ source: "live" }) },
      ],
      "/report": [
        { code: 202, body: WAITING },
        { code: 200, body: samplePack({ source: "live" }) },
      ],
      "/alternatives": [
        { code: 202, body: WAITING },
        { code: 200, body: { source: "live", as_of: "x", matches: [] } },
      ],
    });
    render(<CardPage caseId="7Q2M" variant="result" />);
    for (const id of ["checking-proof", "checking-real", "checking-next", "checking-safer"])
      expect(await screen.findByTestId(id)).toHaveTextContent("Still checking…");
    expect(screen.queryByTestId("case-failed")).toBeNull();

    await waitFor(() => expect(screen.getByTestId("case-real")).toBeInTheDocument(), {
      timeout: 4000,
    });
    await waitFor(() => expect(screen.getByTestId("case-alert")).toBeInTheDocument(), {
      timeout: 4000,
    });
    await waitFor(() => expect(screen.getByTestId("file-pack")).toBeInTheDocument(), {
      timeout: 4000,
    });
    await waitFor(() => expect(screen.queryByTestId("checking-safer")).toBeNull(), {
      timeout: 4000,
    });
    for (const id of ["checking-proof", "checking-real", "checking-next"])
      expect(screen.queryByTestId(id)).toBeNull();
    expect(screen.queryByTestId("case-failed")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not ask for the evidence file when the card says there is none", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({
      "/cases/7Q2M/card": [{ code: 200, body: { ...live, has_evidence: false } }],
    });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-todo")).toBeInTheDocument());
    await new Promise((r) => setTimeout(r, 30));
    expect(calls.filter((c) => c.includes("/evidence"))).toHaveLength(0);
  });

  it("asks for the evidence file when the card says there is one", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({
      "/cases/7Q2M/card": [{ code: 200, body: { ...live, has_evidence: true } }],
    });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(calls.some((c) => c.includes("/evidence"))).toBe(true));
  });
});

describe("apiFetchReadWhenReady", () => {
  it("asks again with a growing wait and gives the 202 back after about 30 s", async () => {
    vi.useFakeTimers();
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({ "/report": [{ code: 202, body: WAITING }] });
    const seen: boolean[] = [];
    const done = apiFetchReadWhenReady("/cases/7Q2M/report", "7Q2M", {}, (w) => seen.push(w));
    await vi.advanceTimersByTimeAsync(READY_WAIT_MS + 5000);
    const res = await done;
    expect(res?.status).toBe(202);
    expect(calls.length).toBeGreaterThan(8);
    expect(calls.length).toBeLessThan(30);
    expect(seen[0]).toBe(true);
    expect(seen.at(-1)).toBe(false);
  });

  it("returns a 200 straight away with no waiting", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({ "/report": [{ code: 200, body: {} }] });
    const res = await apiFetchReadWhenReady("/cases/7Q2M/report", "7Q2M");
    expect(res?.status).toBe(200);
    expect(calls).toHaveLength(1);
  });
});

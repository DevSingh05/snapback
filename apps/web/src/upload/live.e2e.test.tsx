import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { fetchCard, loadCaseReadToken, loadCaseToken } from "../api";
import type { Card } from "../contracts";
import { CardPage } from "../pages/CardPage";
import { UploadPage } from "./UploadPage";

// A mocked server that follows the route shapes in snapback.contracts and the A4 API:
//   POST /cases (multipart) -> 201 CreateCaseResponse (token, challenge_text)
//   POST /cases/{id}/challenge/approve (Bearer token) -> CaseStatus, 401 without the token
//   GET  /cases/{id} -> CaseStatus;  GET /cases/{id}/card -> Card
const TOKEN = "tok_secret_123";
const READ_TOKEN = "tok_read_456";
const liveCard: Card = { ...(cardHold as Card), source: "live" };

interface Call {
  method: string;
  path: string;
  headers: Headers;
  credentials: RequestCredentials | undefined;
  body: unknown;
}

function installServer(opts: { challenge: string | null }) {
  const calls: Call[] = [];
  let status: "waiting_for_approval" | "done" = opts.challenge ? "waiting_for_approval" : "done";
  const json = (body: unknown, code = 200) =>
    new Response(JSON.stringify(body), {
      status: code,
      headers: { "Content-Type": "application/json" },
    });
  const mock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      headers: new Headers(init?.headers),
      credentials: init?.credentials,
      body: init?.body,
    });
    if (method === "GET" && path === "/api/healthz") {
      return json({ status: "ok", data_source: "live" });
    }
    if (method === "POST" && path === "/api/cases") {
      return json(
        {
          case_id: "7Q2M",
          source: "live",
          token: TOKEN,
          read_token: READ_TOKEN,
          status,
          state: status === "done" ? "hold" : null,
          challenge_text: opts.challenge,
          photos: 0,
        },
        201,
      );
    }
    if (method === "POST" && path === "/api/cases/7Q2M/challenge/approve") {
      const auth = new Headers(init?.headers).get("Authorization");
      if (auth !== `Bearer ${TOKEN}`) return json({ detail: "This needs the case's token." }, 401);
      status = "done";
      return json({ case_id: "7Q2M", source: "live", status, state: "hold" });
    }
    if (method === "GET" && path === "/api/cases/7Q2M") {
      return json({ case_id: "7Q2M", source: "live", status, state: null });
    }
    if (method === "GET" && path === "/api/cases/7Q2M/card") return json(liveCard);
    return json({ detail: "nope" }, 404);
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

class FakeEventSource {
  static urls: string[] = [];
  readyState = 1;
  constructor(url: string) {
    FakeEventSource.urls.push(url);
  }
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubEnv("VITE_API_URL", "/api");
  vi.stubGlobal("EventSource", FakeEventSource);
  FakeEventSource.urls = [];
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("web against the API route shapes", () => {
  it("create -> approve with the token -> follow the case to done -> card", async () => {
    const calls = installServer({ challenge: "Send a photo of the door, please." });
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<UploadPage mode="live" navigate={navigate} pollMs={5} />);
    // FIXTURE until /healthz says the API serves live data.
    // The first chip is the card's; the Lab section below has its own (FIXTURE on a 404).
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("LIVE"));

    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    expect(await screen.findByLabelText(/message to forward/i)).toHaveValue(
      "Send a photo of the door, please.",
    );

    // The token is kept in sessionStorage by case id and is not in any URL.
    expect(loadCaseToken("7Q2M")).toBe(TOKEN);
    expect(loadCaseReadToken("7Q2M")).toBe(READ_TOKEN);
    expect(calls.some((c) => c.path.includes(TOKEN))).toBe(false);
    const create = calls.find((c) => c.method === "POST" && c.path === "/api/cases")!;
    expect(create).toMatchObject({ method: "POST", path: "/api/cases", credentials: "include" });
    expect(create.body).toBeInstanceOf(FormData);
    // Nothing was approved by creating the case.
    expect(calls.filter((c) => c.path.endsWith("/challenge/approve"))).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /i approve it/i }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("7Q2M"));

    const approve = calls.find((c) => c.path === "/api/cases/7Q2M/challenge/approve")!;
    expect(approve.method).toBe("POST");
    expect(approve.credentials).toBe("include");
    expect(approve.headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(approve.body as string)).toEqual({ decision: "send" });
    // The page followed the real case: the trace stream and the status poll.
    // EventSource cannot send headers, so the trace carries the secret as ?token= (API PR #60).
    expect(FakeEventSource.urls).toContain(`/api/cases/7Q2M/trace?token=${READ_TOKEN}`);
    expect(FakeEventSource.urls.some((u) => u.includes(TOKEN))).toBe(false);
    const poll = calls.find((c) => c.method === "GET" && c.path === "/api/cases/7Q2M")!;
    expect(poll.headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("a card read from the API shows LIVE", async () => {
    installServer({ challenge: "x" });
    const card = await fetchCard("7Q2M");
    expect(card.source).toBe("live");
    render(<CardPage caseId="7Q2M" variant="result" />);
    expect(await screen.findAllByTestId("source-chip")).not.toHaveLength(0);
    // The first chip is the card's; the Lab section below has its own (FIXTURE on a 404).
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("LIVE"));
  });

  it("with no challenge drafted it skips approval and goes to the card", async () => {
    const calls = installServer({ challenge: null });
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<UploadPage mode="live" navigate={navigate} pollMs={5} />);
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("7Q2M"));
    expect(screen.queryByLabelText(/message to forward/i)).not.toBeInTheDocument();
    expect(calls.filter((c) => c.path.endsWith("/challenge/approve"))).toHaveLength(0);
  });

  it("a refused approval (no token) shows the server's reason and does not move on", async () => {
    installServer({ challenge: "Send a photo, please." });
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<UploadPage mode="live" navigate={navigate} pollMs={5} />);
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await screen.findByLabelText(/message to forward/i);
    window.sessionStorage.clear(); // the token is gone, as in a new tab
    await user.click(screen.getByRole("button", { name: /i approve it/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/401.*needs the case's token/);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe("approval is sent once", () => {
  it("two rapid clicks send exactly one approve request", async () => {
    const calls = installServer({ challenge: "Send a photo, please." });
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<UploadPage mode="live" navigate={navigate} pollMs={5} />);
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    const button = await screen.findByRole("button", { name: /i approve it/i });
    button.click();
    button.click();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("7Q2M"));
    expect(calls.filter((c) => c.path.endsWith("/challenge/approve"))).toHaveLength(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a 409 already-decided answer counts as success and goes on to the case", async () => {
    installServer({ challenge: "Send a photo, please." });
    const real = globalThis.fetch;
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) =>
      url.endsWith("/challenge/approve")
        ? new Response(JSON.stringify({ detail: "This case is not waiting for an approval." }), {
            status: 409,
          })
        : real(url, init),
    );
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<UploadPage mode="live" navigate={navigate} pollMs={5} />);
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await user.click(await screen.findByRole("button", { name: /i approve it/i }));
    expect(
      await screen.findByRole("heading", { name: /waiting for the poster/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

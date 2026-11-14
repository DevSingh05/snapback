import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FinderReply, FinderState } from "../contracts";
import { FinderPage } from "./FinderPage";

// Voice on the Finder: ElevenLabs through our API (mocked here), the browser's recognition only as
// a labelled fallback for input, and never speechSynthesis.

const REPLY = "I put three places up front. The first has a 3D scan and parking.";

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
    learned: {},
    notes: [],
    trace: [],
    as_of: "as of CoStar's last research",
  };
}

interface Opts {
  status?: { tts: boolean; stt: boolean } | null;
  stt?: number; // status code for /voice/stt
  tts?: number;
  heard?: string;
}

function service(opts: Opts = {}) {
  const calls: { url: string; body: unknown }[] = [];
  const json = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const raw = init?.body;
    const body =
      typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw instanceof FormData ? raw : null;
    calls.push({ url, body });
    if (url.endsWith("/voice/status"))
      return opts.status ? json(opts.status) : json({ detail: "no" }, 404);
    if (url.endsWith("/voice/stt"))
      return (opts.stt ?? 200) === 200
        ? json({ text: opts.heard ?? "Pets OK, 2 beds" })
        : json({ reason: "voice not configured" }, opts.stt);
    if (url.endsWith("/voice/tts"))
      return (opts.tts ?? 200) === 200
        ? new Response(new Blob(["ID3fake"], { type: "audio/mpeg" }), { status: 200 })
        : json({ reason: "voice not configured" }, opts.tts);
    if (url.endsWith("/finder/sessions"))
      return json({ session_id: "fs-1", token: "tok", source: "fixture", mode: "deepagents" }, 201);
    if (url.endsWith("/state")) return json(baseState());
    if (url.endsWith("/message")) {
      const reply: FinderReply = {
        session_id: "fs-1",
        source: "fixture",
        mode: "deepagents",
        reply: REPLY,
        reply_by: "model",
        proposals: [],
        picks: [],
        as_of: "as of CoStar's last research",
      };
      return json(reply);
    }
    return json({ detail: "no" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  const sent = () =>
    calls.filter((c) => c.url.endsWith("/message")).map((c) => c.body as { text?: string });
  return { calls, sent };
}

// A MediaRecorder that hands back one small clip when stopped.
const recorders: FakeRecorder[] = [];
class FakeRecorder {
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() {
    recorders.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    if (this.state !== "recording") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["opus"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}
const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: () => undefined }] }));

// The browser's own recognition, for the fallback.
const recognitions: FakeRecognition[] = [];
class FakeRecognition {
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  started = false;
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  constructor() {
    recognitions.push(this);
  }
  start() {
    this.started = true;
  }
  stop() {
    this.onend?.();
  }
  abort() {
    this.onerror?.({ error: "aborted" });
    this.onend?.();
  }
  say(words: string) {
    const result = Object.assign([{ transcript: words }], { isFinal: true });
    this.onresult?.({ results: [result] });
    this.onend?.();
  }
}

let played: HTMLMediaElement[] = [];
const speakSpy = vi.fn();

function withRecorder() {
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  recorders.length = 0;
  recognitions.length = 0;
  played = [];
  getUserMedia.mockClear();
  speakSpy.mockClear();
  vi.stubEnv("VITE_API_URL", "/api");
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    played.push(this);
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  URL.createObjectURL = vi.fn(() => "blob:clip");
  URL.revokeObjectURL = vi.fn();
  // If anything ever reached for the robotic browser voice, this would see it.
  vi.stubGlobal("speechSynthesis", { speak: speakSpy, cancel: vi.fn(), getVoices: () => [] });
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "mediaDevices");
});

async function ready() {
  await screen.findByTestId("finder-status");
}

describe("Finder voice", () => {
  it("hides the mic where the browser can neither record nor recognise speech", async () => {
    service({ status: { tts: true, stt: true } });
    render(<FinderPage />);
    await ready();
    expect(screen.queryByTestId("finder-mic")).toBeNull();
    expect(screen.queryByRole("button", { name: /Talk/ })).toBeNull();
    expect(screen.getByTestId("voice-note")).not.toHaveTextContent("Voice");
  });

  it("offers three example prompts on a first visit, and one tap sends it", async () => {
    const { sent } = service();
    render(<FinderPage />);
    await ready();
    const empty = screen.getByTestId("finder-empty");
    const examples = within(empty).getAllByRole("button");
    expect(examples.map((b) => b.textContent)).toEqual([
      "“Under $1,500, no walk-ups”",
      "“Near downtown with parking”",
      "“Pets OK, 2 beds”",
    ]);
    fireEvent.click(examples[0]!);
    await screen.findByTestId("finder-reply");
    expect(sent()[0]).toMatchObject({ text: "Under $1,500, no walk-ups" });
  });

  it("records a clip, has ElevenLabs write it down on our server, and sends the words", async () => {
    withRecorder();
    const { calls, sent } = service({
      status: { tts: false, stt: true },
      heard: "Pets OK, 2 beds",
    });
    render(<FinderPage />);
    await ready();
    expect(screen.getByTestId("voice-note")).toHaveTextContent(
      "Voice by ElevenLabs. Phone numbers and addresses are removed before the agent reads your words.",
    );
    const mic = screen.getAllByTestId("finder-mic").at(-1)!;
    fireEvent.click(mic);
    await waitFor(() => expect(recorders[0]?.state).toBe("recording"));
    expect(screen.getByTestId("voice-listening")).toHaveTextContent("Listening");
    fireEvent.click(screen.getAllByRole("button", { name: "Stop and send" }).at(-1)!);
    await screen.findByTestId("finder-reply");
    const clip = calls.find((c) => c.url.endsWith("/voice/stt"))!.body as FormData;
    expect(clip.get("audio")).toBeInstanceOf(Blob);
    expect(sent()[0]).toMatchObject({ text: "Pets OK, 2 beds" });
    expect(screen.getByTestId("finder-msg")).toHaveTextContent("Pets OK, 2 beds");
  });

  it("speaks each reply through /voice/tts when Read replies aloud is on, and remembers it", async () => {
    const { calls } = service({ status: { tts: true, stt: false } });
    render(<FinderPage />);
    await ready();
    const toggle = await screen.findByRole("switch", { name: /Read replies aloud/ });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    fireEvent.click(toggle);
    expect(window.localStorage.getItem("snapback.finder-read-aloud")).toBe("on");
    fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(played).toHaveLength(1), { timeout: 5000 });
    expect(calls.find((c) => c.url.endsWith("/voice/tts"))!.body).toEqual({ text: REPLY });
    expect(speakSpy).not.toHaveBeenCalled();
    // A per-reply button plays it again.
    const reply = screen.getByTestId("finder-reply");
    expect(within(reply).getByRole("button", { name: "Stop reading" })).toBeInTheDocument();
  }, 15_000);

  it("talk mode opens the mic again once the spoken reply ends", async () => {
    withRecorder();
    service({ status: { tts: true, stt: true }, heard: "Near downtown with parking" });
    render(<FinderPage />);
    await ready();
    await screen.findByRole("switch", { name: /Read replies aloud/ });
    fireEvent.click(screen.getByRole("button", { name: "Talk" }));
    await waitFor(() => expect(recorders[0]?.state).toBe("recording"));
    expect(screen.getByTestId("talk-bar")).toHaveTextContent("Talk mode · Listening");
    fireEvent.click(screen.getAllByRole("button", { name: "Stop and send" }).at(-1)!);
    await waitFor(() => expect(played).toHaveLength(1), { timeout: 5000 });
    expect(recorders).toHaveLength(1);
    act(() => {
      played[0]!.dispatchEvent(new Event("ended"));
    });
    await waitFor(() => expect(recorders[1]?.state).toBe("recording"), { timeout: 5000 });
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: /End talk/ }));
    expect(screen.queryByTestId("talk-bar")).toBeNull();
  }, 15_000);

  it("hides read-aloud when /voice/tts says voice is not configured, with no browser voice", async () => {
    service({ status: { tts: true, stt: false }, tts: 503 });
    render(<FinderPage />);
    await ready();
    fireEvent.click(await screen.findByRole("switch", { name: /Read replies aloud/ }));
    fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByTestId("finder-reply");
    await waitFor(() => expect(screen.queryByRole("switch")).toBeNull());
    expect(played).toHaveLength(0);
    expect(speakSpy).not.toHaveBeenCalled();
  });

  it("falls back to the browser's recognition for input when /voice/stt is not configured", async () => {
    withRecorder();
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    const { sent } = service({ status: { tts: false, stt: true }, stt: 503 });
    render(<FinderPage />);
    await ready();
    fireEvent.click(screen.getAllByTestId("finder-mic").at(-1)!);
    await waitFor(() => expect(recorders[0]?.state).toBe("recording"));
    fireEvent.click(screen.getAllByRole("button", { name: "Stop and send" }).at(-1)!);
    await waitFor(() =>
      expect(screen.getByTestId("voice-note")).toHaveTextContent(
        "Voice uses your browser's speech recognition.",
      ),
    );
    expect(sent()).toHaveLength(0); // nothing was heard, so nothing was sent
    fireEvent.click(screen.getAllByTestId("finder-mic").at(-1)!);
    expect(recognitions[0]?.started).toBe(true);
    act(() => recognitions[0]!.say("Under $1,500, no walk-ups"));
    await screen.findByTestId("finder-reply");
    expect(sent()[0]).toMatchObject({ text: "Under $1,500, no walk-ups" });
  });

  it("works offline with the browser's recognition only, and says so", () => {
    vi.unstubAllEnvs();
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    render(<FinderPage />);
    expect(screen.getByTestId("voice-note")).toHaveTextContent(
      "Voice uses your browser's speech recognition.",
    );
    fireEvent.click(screen.getAllByTestId("finder-mic").at(-1)!);
    act(() => recognitions[0]!.say("no walk-ups please"));
    expect(screen.getByTestId("finder-msg")).toHaveTextContent("no walk-ups please");
  });
});

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useVoiceInput } from "./voice";

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

beforeEach(() => {
  recorders.length = 0;
  vi.stubEnv("VITE_API_URL", "/api");
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: () => undefined }] })) },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ text: "Near downtown with parking" }, { status: 200 })),
  );
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "mediaDevices");
});

describe("useVoiceInput", () => {
  it("opens the mic again from a callback that runs before React renders the end of the turn", async () => {
    // Talk mode does exactly this: the reply's audio ends and the mic re-opens, possibly before
    // React has rendered the last turn going idle. `start` must see the turn as over.
    const heard: string[] = [];
    const { result } = renderHook(() =>
      useVoiceInput({
        server: true,
        onWords: (words) => {
          heard.push(words);
          result.current.start(true);
        },
      }),
    );
    expect(result.current.engine).toBe("eleven");
    act(() => result.current.start(true));
    await waitFor(() => expect(recorders[0]?.state).toBe("recording"));
    act(() => result.current.stop());
    await waitFor(() => expect(heard).toEqual(["Near downtown with parking"]));
    await waitFor(() => expect(recorders[1]?.state).toBe("recording"));
    expect(result.current.state).toBe("recording");
  });

  it("still refuses to start a second turn while one is being written down", async () => {
    let finish: (r: Response) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => (finish = resolve))),
    );
    const { result } = renderHook(() => useVoiceInput({ server: true, onWords: () => undefined }));
    act(() => result.current.start(true));
    await waitFor(() => expect(recorders[0]?.state).toBe("recording"));
    act(() => result.current.stop());
    await waitFor(() => expect(result.current.state).toBe("writing"));
    act(() => result.current.start(true));
    expect(recorders).toHaveLength(1);
    await act(async () => finish(Response.json({ text: "" })));
    await waitFor(() => expect(result.current.state).toBe("idle"));
  });
});

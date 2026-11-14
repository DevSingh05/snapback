// Voice for the Finder. Speech goes through our own API to ElevenLabs (api/voice.py): the mic
// records a clip with MediaRecorder and /voice/stt writes it down (Scribe); replies come back from
// /voice/tts as audio and play in an Audio element. The key never reaches the browser. When the
// server has no voice key, input falls back to the browser's own speech recognition (labelled as
// such) and read-aloud is hidden: there is no robotic speechSynthesis fallback on purpose.
import { useCallback, useEffect, useRef, useState } from "react";

import { apiBase } from "../api";

/** The server has no voice key (503 {"reason": "voice not configured"}). */
export class VoiceOff extends Error {}

export interface VoiceStatus {
  tts: boolean;
  stt: boolean;
}

export const MAX_CLIP_SECONDS = 60;

export async function voiceStatus(): Promise<VoiceStatus> {
  const base = apiBase();
  if (!base) return { tts: false, stt: false };
  try {
    const res = await fetch(`${base}/voice/status`);
    if (!res.ok) return { tts: false, stt: false };
    const body = (await res.json()) as Partial<VoiceStatus>;
    return { tts: body.tts === true, stt: body.stt === true };
  } catch {
    return { tts: false, stt: false };
  }
}

async function reasonOf(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { reason?: unknown; detail?: unknown };
    if (typeof body.reason === "string") return body.reason;
  } catch {
    // not JSON
  }
  return fallback;
}

/** What the renter said, written down by Scribe and cleaned by the server's sanitiser. */
export async function transcribe(clip: Blob, seconds: number): Promise<string> {
  const base = apiBase();
  if (!base) throw new VoiceOff("No API is configured.");
  const form = new FormData();
  const ext = clip.type.includes("mp4") ? "m4a" : clip.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", clip, `clip.${ext}`);
  form.append("seconds", seconds.toFixed(1));
  let res: Response;
  try {
    res = await fetch(`${base}/voice/stt`, { method: "POST", body: form });
  } catch {
    throw new Error("Voice did not reach the server. Type instead.");
  }
  if (res.status === 503) throw new VoiceOff("voice not configured");
  if (!res.ok) throw new Error(await reasonOf(res, "Voice could not hear that. Try again."));
  const body = (await res.json()) as { text?: unknown };
  return typeof body.text === "string" ? body.text.trim() : "";
}

/** A reply as speech, from ElevenLabs through our API. */
export async function synthesize(text: string): Promise<Blob> {
  const base = apiBase();
  if (!base) throw new VoiceOff("No API is configured.");
  const res = await fetch(`${base}/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.slice(0, 600) }),
  });
  if (res.status === 503) throw new VoiceOff("voice not configured");
  if (!res.ok) throw new Error(await reasonOf(res, "Could not read that aloud."));
  return res.blob();
}

// ---------------------------------------------------------------------------------------------
// Read aloud: remembered on this device.

const READ_KEY = "snapback.finder-read-aloud";

export function loadReadAloud(): boolean {
  try {
    return window.localStorage.getItem(READ_KEY) === "on";
  } catch {
    return false;
  }
}

export function saveReadAloud(on: boolean): void {
  try {
    window.localStorage.setItem(READ_KEY, on ? "on" : "off");
  } catch {
    // Storage blocked: the choice lasts until the page reloads.
  }
}

// ---------------------------------------------------------------------------------------------
// Recording.

export function canRecord(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder === "function" &&
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}

// The slice of SpeechRecognition the fallback uses, declared here so the page does not depend on
// a lib.dom version that ships (or drops) these types.
interface RecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: { transcript: string };
}
export interface RecognitionEvent {
  readonly results: { readonly length: number; [index: number]: RecognitionResult };
}
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

export function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const MIC_ERRORS: Record<string, string> = {
  NotAllowedError: "The microphone is blocked. Allow it for this site to talk.",
  "not-allowed": "The microphone is blocked. Allow it for this site to talk.",
  NotFoundError: "No microphone was found.",
  "audio-capture": "No microphone was found.",
  "service-not-allowed": "This browser does not allow speech recognition here.",
  network: "Speech recognition needs a connection. Type instead.",
};

/** Seconds of quiet, after some speech, that end a hands-free turn. */
const QUIET_ENDS_TURN = 1.3;
/** Seconds of nothing at all before a hands-free turn gives up. */
const NOTHING_HEARD = 9;
const SPEECH_LEVEL = 0.06;

export type VoiceEngine = "eleven" | "browser";
export type MicState = "idle" | "recording" | "writing";

/**
 * One mic for the Finder. `engine` says who writes the words down: ElevenLabs through our API, or
 * the browser's own recognition when the server has no voice key. start(handsFree) opens the mic;
 * hands-free ends by itself after a pause (talk mode). stop() ends and sends what was heard;
 * cancel() drops it. onWords gets the final words; onSilence runs when nothing was heard.
 */
export function useVoiceInput({
  server,
  onWords,
  onSilence,
}: {
  server: boolean;
  onWords: (words: string) => void;
  onSilence?: () => void;
}) {
  const [serverOff, setServerOff] = useState(false);
  const recordable = canRecord();
  const Recog = recognitionCtor();
  const engine: VoiceEngine | null =
    server && !serverOff && recordable ? "eleven" : Recog ? "browser" : null;

  const [state, setState] = useState<MicState>("idle");
  const [level, setLevel] = useState(0);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const cbs = useRef({ onWords, onSilence });
  useEffect(() => {
    cbs.current = { onWords, onSilence };
  });

  // Live handles, so stop and cancel reach whatever is running.
  const live = useRef<{
    stop: () => void;
    cancel: () => void;
  } | null>(null);

  const teardown = useRef<(() => void) | null>(null);
  useEffect(
    () => () => {
      live.current?.cancel();
      teardown.current?.();
    },
    [],
  );

  const startBrowser = useCallback(() => {
    if (!Recog) return;
    const r = new Recog();
    r.lang = "en-US";
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    let heard = "";
    let dropped = false;
    r.onresult = (e) => {
      let done = "";
      let partial = "";
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i]!;
        if (res.isFinal) done += res[0]?.transcript ?? "";
        else partial += res[0]?.transcript ?? "";
      }
      heard = done.trim();
      setInterim(`${done}${partial}`.trim());
      setLevel(partial || done ? 0.5 : 0);
    };
    r.onerror = (e) => {
      if (e.error === "aborted") dropped = true;
      else if (e.error !== "no-speech")
        setError(MIC_ERRORS[e.error] ?? "Voice stopped. Try again.");
    };
    r.onend = () => {
      live.current = null;
      setState("idle");
      setInterim("");
      setLevel(0);
      if (dropped) return;
      if (heard) cbs.current.onWords(heard);
      else cbs.current.onSilence?.();
    };
    live.current = {
      stop: () => r.stop(),
      cancel: () => {
        dropped = true;
        r.abort();
      },
    };
    try {
      r.start();
      setState("recording");
    } catch {
      live.current = null;
      setError("Voice could not start. Try again.");
    }
  }, [Recog]);

  const startEleven = useCallback(async (handsFree: boolean) => {
    let stream: MediaStream;
    setState("recording");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      setState("idle");
      const name = err instanceof Error ? err.name : "";
      setError(MIC_ERRORS[name] ?? "The microphone could not start.");
      return;
    }
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    const began = performance.now();
    let dropped = false;
    let spoke = false;
    let lastLoud = began;
    let frame = 0;
    let ctx: AudioContext | null = null;
    const timers: number[] = [];

    const close = () => {
      cancelAnimationFrame(frame);
      timers.forEach((t) => window.clearTimeout(t));
      stream.getTracks().forEach((t) => t.stop());
      void ctx?.close().catch(() => undefined);
      ctx = null;
      setLevel(0);
    };
    teardown.current = close;

    // The level meter, and in hands-free mode the pause that ends the turn.
    try {
      const AC =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AC) {
        ctx = new AC();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(buf);
          let sum = 0;
          for (const v of buf) sum += ((v - 128) / 128) ** 2;
          const rms = Math.sqrt(sum / buf.length);
          const lvl = Math.min(1, rms * 5);
          setLevel(lvl);
          const now = performance.now();
          if (lvl > SPEECH_LEVEL) {
            spoke = true;
            lastLoud = now;
          }
          if (handsFree && rec.state === "recording") {
            if (spoke && now - lastLoud > QUIET_ENDS_TURN * 1000) rec.stop();
            else if (!spoke && now - began > NOTHING_HEARD * 1000) {
              dropped = true;
              rec.stop();
              cbs.current.onSilence?.();
            }
          }
          frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      }
    } catch {
      // No meter on this browser; recording still works.
    }

    rec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };
    rec.onstop = async () => {
      close();
      live.current = null;
      if (dropped) {
        setState("idle");
        return;
      }
      const seconds = (performance.now() - began) / 1000;
      const clip = new Blob(chunks, { type: rec.mimeType || chunks[0]?.type || "audio/webm" });
      if (clip.size === 0) {
        setState("idle");
        cbs.current.onSilence?.();
        return;
      }
      setState("writing");
      try {
        const words = await transcribe(clip, Math.min(seconds, MAX_CLIP_SECONDS));
        setState("idle");
        if (words) cbs.current.onWords(words);
        else cbs.current.onSilence?.();
      } catch (err) {
        setState("idle");
        if (err instanceof VoiceOff) {
          setServerOff(true);
          setNote(
            "ElevenLabs voice is not set up on this server, so the mic now uses your browser's speech recognition. Say it once more.",
          );
        } else setError(err instanceof Error ? err.message : "Voice could not hear that.");
      }
    };
    timers.push(
      window.setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, MAX_CLIP_SECONDS * 1000),
    );
    live.current = {
      stop: () => {
        if (rec.state === "recording") rec.stop();
      },
      cancel: () => {
        dropped = true;
        if (rec.state === "recording") rec.stop();
        else close();
      },
    };
    rec.start();
  }, []);

  const start = useCallback(
    (handsFree = false) => {
      if (live.current || state !== "idle" || !engine) return;
      setError(null);
      setNote(null);
      setInterim("");
      if (engine === "eleven") void startEleven(handsFree);
      else startBrowser();
    },
    [engine, startBrowser, startEleven, state],
  );
  const stop = useCallback(() => live.current?.stop(), []);
  const cancel = useCallback(() => live.current?.cancel(), []);

  return { engine, state, level, interim, error, note, start, stop, cancel };
}

// ---------------------------------------------------------------------------------------------
// Playback: one Audio element for the page.

export function usePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const done = useRef<(() => void) | null>(null);

  const stop = useCallback(() => {
    const a = audio.current;
    done.current = null;
    if (a) {
      a.pause();
      a.removeAttribute("src");
    }
  }, []);

  const play = useCallback(
    async (url: string, onEnd: () => void) => {
      stop();
      const a = audio.current ?? new Audio();
      audio.current = a;
      done.current = onEnd;
      const finish = () => {
        const cb = done.current;
        done.current = null;
        cb?.();
      };
      a.onended = finish;
      a.onerror = finish;
      a.src = url;
      try {
        await a.play();
      } catch {
        finish();
      }
    },
    [stop],
  );

  useEffect(() => stop, [stop]);
  return { play, stop };
}

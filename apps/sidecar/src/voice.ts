/**
 * Voice memos in iMessage (Photon Best Voice Agent): a renter can say the ad instead of typing it,
 * and a spoken ad gets the card back as text plus a voice memo, in the same voice as the app.
 *
 * - Speech goes only to our own API: `POST /voice/stt` (multipart `audio`, plus `seconds` when
 *   known; returns `{text}`) and `POST /voice/tts` (`{text}`, at most 600 characters, returns
 *   audio). The API holds the ElevenLabs key; the sidecar never sees one.
 * - One cap on both sides: MAX_VOICE_SECONDS, the same 60 s the API checks. Photon's iMessage
 *   provider sends no duration, so a memo is first refused by size (MAX_VOICE_BYTES, before it is
 *   downloaded), then by the length ffmpeg measures while converting.
 * - Apple sends memos as CAF. It is converted to mono m4a with ffmpeg (the same binary the Photon
 *   SDK uses to send audio), which is killed after FFMPEG_TIMEOUT_MS.
 * - Replies: 503 means voice is not set up; a 413 or a memo over the cap means too long; an empty
 *   transcript, a failed conversion or any other error means "I couldn't hear that".
 * - The transcript is treated exactly like typed text: the same ad check, the same limits. Watch
 *   alerts stay text only.
 */

import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const MAX_VOICE_SECONDS = 60;
export const MAX_VOICE_BYTES = 400 * 1024; // about 2 minutes of Apple's Opus memo: a first, coarse cut
export const FFMPEG_TIMEOUT_MS = 20_000;
const MAX_TTS_CHARS = 600;

export const VOICE_TOO_LONG =
  "Please keep voice memos under a minute. You can also type or paste the ad.";
export const VOICE_OFF =
  "Voice memos are not set up right now. Please type or paste the ad instead. Don't pay anyone yet.";
export const VOICE_UNHEARD =
  "I couldn't hear that. Please type or paste the ad. Don't pay anyone yet.";

export type Audio = { bytes: Uint8Array; mimeType: string; seconds?: number };
export type ConvertVoice = (bytes: Uint8Array, mimeType: string) => Promise<Audio>;
export type Heard = { text: string } | { fail: "off" | "too_long" | "unheard" };

/** True when Apple's CAF (or an unknown type) must be converted before speech to text. */
export function needsConversion(mimeType: string): boolean {
  return !/^audio\/(mp4|m4a|x-m4a|aac|mpeg|mp3|wav|x-wav|webm|ogg)$/i.test(mimeType);
}

/** ffmpeg's "Duration: 00:01:05.20" for the input, in seconds, or undefined. */
export function durationFrom(stderr: string): number | undefined {
  const m = /Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/.exec(stderr);
  if (!m) return undefined;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

/** CAF (or anything ffmpeg reads) to mono m4a, through a temporary folder that is always
 * removed. Stops after MAX_VOICE_SECONDS + 1 s of audio and is killed after FFMPEG_TIMEOUT_MS. */
export const ffmpegToM4a: ConvertVoice = async (bytes) => {
  const dir = await mkdtemp(join(tmpdir(), "snapback-voice-"));
  const input = join(dir, "in");
  const output = join(dir, "out.m4a");
  try {
    await writeFile(input, bytes);
    const args = ["-y", "-i", input, "-t", String(MAX_VOICE_SECONDS + 1), "-ac", "1"];
    args.push("-b:a", "48k", "-f", "ipod", "-c:a", "aac", output);
    const stderr = await new Promise<string>((done, fail) => {
      const ff = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
      let log = "";
      ff.stderr?.on("data", (chunk: Buffer) => void (log = (log + chunk.toString()).slice(-8000)));
      const timer = setTimeout(() => ff.kill("SIGKILL"), FFMPEG_TIMEOUT_MS);
      ff.on("error", (error) => {
        clearTimeout(timer);
        fail(error);
      });
      ff.on("close", (code) => {
        clearTimeout(timer);
        if (code === 0) done(log);
        else fail(new Error(`ffmpeg stopped (${code ?? "killed"})`));
      });
    });
    const out = new Uint8Array(await readFile(output));
    // the input's own length; if ffmpeg cannot tell, estimate it from the 48 kbit/s output
    const seconds = durationFrom(stderr) ?? (out.length * 8) / 48_000;
    return { bytes: out, mimeType: "audio/mp4", seconds };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
};

/** The memo written down by our API, or why it could not be. */
export async function transcribe(
  audio: Audio,
  apiUrl: string,
  get: typeof fetch,
  convert: ConvertVoice,
): Promise<Heard> {
  let clip: Audio;
  try {
    clip = needsConversion(audio.mimeType) ? await convert(audio.bytes, audio.mimeType) : audio;
  } catch {
    return { fail: "unheard" };
  }
  const seconds = clip.seconds ?? audio.seconds;
  if (seconds !== undefined && seconds > MAX_VOICE_SECONDS) return { fail: "too_long" };
  const ext = clip.mimeType.includes("mp4") || clip.mimeType.includes("m4a") ? "m4a" : "audio";
  const form = new FormData();
  const blob = new Blob([new Uint8Array(clip.bytes)], { type: clip.mimeType });
  form.append("audio", blob, `memo.${ext}`);
  if (seconds !== undefined) form.append("seconds", String(Math.round(seconds)));
  let res: Response;
  try {
    res = await get(`${apiUrl.replace(/\/$/, "")}/voice/stt`, { method: "POST", body: form });
  } catch {
    return { fail: "unheard" };
  }
  if (res.status === 503) return { fail: "off" };
  if (res.status === 413) return { fail: "too_long" };
  if (!res.ok) return { fail: "unheard" };
  const body = (await res.json().catch(() => ({}))) as { text?: unknown };
  const text = typeof body.text === "string" ? body.text.trim() : "";
  // the API strips numbers it must not keep as "[removed]": nothing else left means not heard
  if (!text.replace(/\[removed\]/gi, "").trim()) return { fail: "unheard" };
  return { text };
}

/** The reply for a memo that could not be written down. */
export function heardFailure(fail: "off" | "too_long" | "unheard"): string {
  return fail === "off" ? VOICE_OFF : fail === "too_long" ? VOICE_TOO_LONG : VOICE_UNHEARD;
}

/** What the voice reply says: the card's locked headline and a pointer to the text. */
export function spokenReply(replyText: string): string {
  const headline = (replyText.split("\n")[0] ?? "").replace(/[.!]*$/, "");
  return `${headline}. I sent the details and a link as a text.`.slice(0, MAX_TTS_CHARS);
}

/** The spoken reply as audio from our API, or null if voice is off or the call failed. */
export async function speak(
  text: string,
  apiUrl: string,
  get: typeof fetch,
): Promise<Audio | null> {
  const res = await get(`${apiUrl.replace(/\/$/, "")}/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.slice(0, MAX_TTS_CHARS) }),
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  return { bytes: new Uint8Array(await blob.arrayBuffer()), mimeType: blob.type || "audio/mpeg" };
}

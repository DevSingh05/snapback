/**
 * Voice memos in iMessage (Photon Best Voice Agent): a renter can say the ad instead of typing it,
 * and a spoken ad gets the card back as text plus a voice memo, in the same voice as the app.
 *
 * - Speech goes only to our own API: `POST /voice/stt` (multipart `audio`, returns `{text}`) and
 *   `POST /voice/tts` (`{text}`, at most 600 characters, returns audio). The API holds the
 *   ElevenLabs key; the sidecar never sees one.
 * - Apple sends memos as CAF. It is converted to m4a before speech to text (ffmpeg, the same
 *   binary the Photon SDK uses to send audio).
 * - Memos over MAX_VOICE_SECONDS or MAX_VOICE_BYTES are never downloaded or sent anywhere.
 * - The transcript is treated exactly like typed text: the same ad check, the same limits. Watch
 *   alerts stay text only.
 */

import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const MAX_VOICE_SECONDS = 120;
export const MAX_VOICE_BYTES = 10 * 1024 * 1024;
const MAX_TTS_CHARS = 600;

export const VOICE_TOO_LONG =
  "Please keep voice memos under 2 minutes. You can also type or paste the ad.";
export const VOICE_OFF =
  "Voice memos are not set up right now. Please type or paste the ad instead. Don't pay anyone yet.";

export type Audio = { bytes: Uint8Array; mimeType: string };
export type ConvertVoice = (bytes: Uint8Array, mimeType: string) => Promise<Audio>;

/** True when Apple's CAF (or an unknown type) must be converted before speech to text. */
export function needsConversion(mimeType: string): boolean {
  return !/^audio\/(mp4|m4a|x-m4a|aac|mpeg|mp3|wav|x-wav|webm|ogg)$/i.test(mimeType);
}

/** CAF (or anything ffmpeg reads) to m4a, through a temporary folder that is always removed. */
export const ffmpegToM4a: ConvertVoice = async (bytes) => {
  const dir = await mkdtemp(join(tmpdir(), "snapback-voice-"));
  const input = join(dir, "in");
  const output = join(dir, "out.m4a");
  try {
    await writeFile(input, bytes);
    await new Promise<void>((done, fail) => {
      const ff = spawn("ffmpeg", ["-y", "-i", input, "-f", "ipod", "-c:a", "aac", output], {
        stdio: "ignore",
      });
      ff.on("error", fail);
      ff.on("close", (code) => (code === 0 ? done() : fail(new Error(`ffmpeg exited ${code}`))));
    });
    return { bytes: new Uint8Array(await readFile(output)), mimeType: "audio/mp4" };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
};

/** The memo written down by our API, or null if voice is off or the call failed. */
export async function transcribe(
  audio: Audio,
  apiUrl: string,
  get: typeof fetch,
  convert: ConvertVoice,
): Promise<string | null> {
  const clip = needsConversion(audio.mimeType) ? await convert(audio.bytes, audio.mimeType) : audio;
  const ext = clip.mimeType.includes("mp4") || clip.mimeType.includes("m4a") ? "m4a" : "audio";
  const form = new FormData();
  form.append(
    "audio",
    new Blob([new Uint8Array(clip.bytes)], { type: clip.mimeType }),
    `memo.${ext}`,
  );
  const res = await get(`${apiUrl.replace(/\/$/, "")}/voice/stt`, { method: "POST", body: form });
  if (!res.ok) return null;
  const body = (await res.json()) as { text?: unknown };
  const text = typeof body.text === "string" ? body.text.trim() : "";
  return text || null;
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

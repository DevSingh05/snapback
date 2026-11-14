/**
 * Photon (Spectrum, iMessage) for the sidecar (D4, #38): renter messages in, the card back out.
 *
 * Only the parts of `spectrum-ts` the sidecar uses are typed here, so the loop is tested with a
 * fake app and CI never needs an account. The SDK is loaded only when a project is configured.
 *
 * Hard rules, on top of handler.ts:
 * - SNAPBACK texts first ONLY in a thread that linked a Finder watch with "watch <code>"
 *   (Vidyut's ruling R-M1, M10): at most 3 a day, and a stop word ends it for good (watch.ts). Every other send is `space.send`, on
 *   the space an inbound message came from, after that message: every other thread stays
 *   reply-only. Outbound messages (our own echoes) are skipped.
 * - Only allowlisted threads get anything back, and nothing is checked for any other thread.
 * - Nothing about a renter is logged: no thread id, no handle, no words. A thread that is not
 *   on the allowlist is logged by its keyed hash only, which is what the allowlist can hold.
 * - The project secret is passed to the SDK and never logged.
 */

import {
  CHECKING,
  handleMessage,
  isAllowed,
  renterId,
  type InboundMessage,
  type SidecarConfig,
} from "./handler";
import {
  MAX_VOICE_BYTES,
  MAX_VOICE_SECONDS,
  VOICE_TOO_LONG,
  heardFailure,
  ffmpegToM4a,
  speak,
  spokenReply,
  transcribe,
  type Audio,
  type ConvertVoice,
} from "./voice";
import { answerCommand, type WatchBook } from "./watch";

export type PhotonContent =
  | { type: "text"; text: string }
  | { type: "attachment"; mimeType: string; size?: number; read: () => Promise<Uint8Array> }
  | { type: "richlink"; url: string }
  // a voice memo (Apple sends CAF); `duration` in seconds
  | {
      type: "voice";
      mimeType: string;
      duration?: number;
      size?: number;
      read: () => Promise<Uint8Array>;
    }
  // more than one part in one send (a caption and a photo), and a swipe-reply
  | { type: "group"; items: { content: PhotonContent }[] }
  | { type: "reply"; content: PhotonContent }
  | { type: string };

export type PhotonMessage = { direction: "inbound" | "outbound"; content: PhotonContent };

/** `send` takes text, or what the SDK's `voice()` builder returns (see `makeVoice`). */
export type PhotonSpace = { id: string; send(content: unknown): Promise<unknown> };

export type PhotonApp = {
  messages: AsyncIterable<[PhotonSpace, PhotonMessage]>;
  stop?: () => Promise<void>;
};

export type PhotonConfig = SidecarConfig & {
  /** A renter often sends the ad and its photos as separate messages: wait this long after
   * the last one, then check them together. */
  quietMs?: number;
  /** A photo larger than this is not downloaded (SNAPBACK_MAX_PHOTO_MB). */
  maxPhotoBytes?: number;
  /** Watch alerts (M10). Without it, "watch" and "stop" are read as any other text. */
  watches?: WatchBook;
  /** Voice replies: the SDK's `voice(buffer, { mimeType })` builder. Without it, text only. */
  makeVoice?: (bytes: Uint8Array, mimeType: string) => unknown;
  /** U1: one "checking" reply per batch before a new check (not for follow-ups). */
  acknowledge?: boolean;
  /** The card picture: the SDK's `attachment(buffer, { mimeType, name })`. Without it, text only. */
  makeImage?: (bytes: Uint8Array, mimeType: string) => unknown;
  /** CAF to m4a before speech to text. Defaults to ffmpeg. */
  convertVoice?: ConvertVoice;
};

type Log = (line: string) => void;

const QUIET_MS = 4000;
const MAX_PHOTOS = 10;
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i;

/** The public site the reply links to. With Photon on, a renter's phone must be able to open
 * it: unset or localhost refuses to start (review of #204). */
export function publicWebUrl(env: Record<string, string | undefined>): string {
  const url = (env.WEB_URL ?? "").trim();
  if (!url || LOCAL.test(url)) {
    throw new Error("Photon is on, so WEB_URL must be the public site the reply links to.");
  }
  return url;
}

type Pending = {
  space: PhotonSpace;
  texts: string[];
  images: Blob[];
  voices?: Audio[]; // memos to write down before the check
  notes?: string[]; // things to tell the renter when nothing can be checked (a memo too long)
  timer?: NodeJS.Timeout;
};

type Limits = { maxPhotos: number; maxPhotoBytes: number; skipped: string[] };

/** Read one message's content into the pending check for its space. False if nothing usable;
 * the type of anything that cannot be read is noted in `limits.skipped` (no content). */
async function collect(pending: Pending, content: PhotonContent, limits: Limits): Promise<boolean> {
  if (content.type === "group" && "items" in content) {
    let used = false;
    for (const item of content.items) used = (await collect(pending, item.content, limits)) || used;
    return used;
  }
  if (content.type === "reply" && "content" in content) {
    return collect(pending, content.content, limits);
  }
  if (content.type === "text" && "text" in content) {
    pending.texts.push(content.text);
    return true;
  }
  if (content.type === "richlink" && "url" in content) {
    pending.texts.push(content.url);
    return true;
  }
  if (content.type === "voice" && "read" in content) {
    // never download a memo over the caps: it is not written down or sent anywhere
    const long = "duration" in content && (content.duration ?? 0) > MAX_VOICE_SECONDS;
    const big = (content.size ?? 0) > MAX_VOICE_BYTES;
    if (long || big) {
      limits.skipped.push("voice memo over the limit");
      pending.notes = [...(pending.notes ?? []), VOICE_TOO_LONG];
      return true;
    }
    const bytes = await content.read();
    if (bytes.length > MAX_VOICE_BYTES) {
      pending.notes = [...(pending.notes ?? []), VOICE_TOO_LONG];
      return true;
    }
    pending.voices = [...(pending.voices ?? []), { bytes, mimeType: content.mimeType }];
    return true;
  }
  if (content.type === "attachment" && "read" in content && content.mimeType.startsWith("image/")) {
    // never download what will not be sent: past the photo limit, or over the size limit
    if (pending.images.length >= limits.maxPhotos) return false;
    if ((content.size ?? 0) > limits.maxPhotoBytes) {
      limits.skipped.push("photo over the size limit");
      return false;
    }
    const bytes = await content.read();
    pending.images.push(new Blob([new Uint8Array(bytes)], { type: content.mimeType }));
    return true;
  }
  limits.skipped.push(content.type);
  return false;
}

/** Run the loop until the message stream ends. Every send is a reply in the renter's thread. */
export async function runPhoton(app: PhotonApp, config: PhotonConfig, log: Log = console.log) {
  const pending = new Map<string, Pending>();
  const running: Promise<void>[] = [];
  const quietMs = config.quietMs ?? QUIET_MS;

  const get = config.fetch ?? fetch;

  /** Check what the renter sent (writing down any voice memo first), then reply. */
  const answer = async (item: Pending): Promise<void> => {
    const spoken = (item.voices?.length ?? 0) > 0;
    for (const audio of item.voices ?? []) {
      const convert = config.convertVoice ?? ffmpegToM4a;
      const heard = await transcribe(audio, config.apiUrl, get, convert);
      if ("text" in heard) item.texts.push(heard.text);
      else if (item.texts.length === 0 && item.images.length === 0) {
        // nothing to check without the words: say why (off, too long, or not heard)
        await item.space.send(heardFailure(heard.fail));
        return;
      }
    }
    if (item.texts.length === 0 && item.images.length === 0) {
      for (const note of item.notes ?? []) await item.space.send(note);
      return;
    }
    const msg: InboundMessage = {
      threadId: item.space.id,
      text: item.texts.join("\n"),
      imageUrls: [],
      images: item.images,
      receivedAt: new Date().toISOString(),
    };
    let replied = "";
    // The client is bound to this space: it cannot send anywhere else.
    const client = {
      async reply(threadId: string, text: string) {
        if (threadId !== item.space.id) throw new Error("a reply may only go to its own thread");
        await item.space.send(text);
        replied = text;
      },
      // the card picture, through the SDK's attachment builder, to the same space only
      ...(config.makeImage
        ? {
            async image(threadId: string, bytes: Uint8Array, mimeType: string) {
              if (threadId !== item.space.id)
                throw new Error("a reply may only go to its own thread");
              await item.space.send(config.makeImage!(bytes, mimeType));
            },
          }
        : {}),
    };
    const checking = config.acknowledge
      ? async () => void (await item.space.send(CHECKING))
      : undefined;
    await handleMessage(msg, client, config, checking);
    if (!spoken || !replied || !config.makeVoice) return;
    // A spoken ad gets a spoken answer too. If it fails, the text has already gone out.
    try {
      const audio = await speak(spokenReply(replied), config.apiUrl, get);
      if (audio) await item.space.send(config.makeVoice(audio.bytes, audio.mimeType));
    } catch {
      log("[sidecar] a voice reply could not be sent; the text reply went out");
    }
  };

  const flush = (id: string) => {
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    running.push(
      answer(item).then(
        () => log("[sidecar] replied in an allowed thread"),
        () => log("[sidecar] a reply could not be sent"),
      ),
    );
  };

  for await (const [space, message] of app.messages) {
    if (message.direction !== "inbound") continue;
    if (!isAllowed(space.id, config)) {
      log(
        `[sidecar] ignored a thread not on the allowlist (${renterId(space.id, config.renterSalt)})`,
      );
      continue;
    }
    if (config.watches) {
      const answer = answerCommand(message.content, space, config.watches, config.webUrl, log);
      if (answer !== null) {
        // "watch <code>" and a stop word are answered at once, in the same thread, and never
        // checked; a swipe-reply "stop" counts too
        try {
          await space.send(answer);
        } catch {
          log("[sidecar] a reply could not be sent");
        }
        continue;
      }
    }
    const item = pending.get(space.id) ?? { space, texts: [], images: [] };
    // Stop the wait while this message is read, so a slow download cannot let the check go
    // out without it (and then go out again with it: two of the day's checks for one ad).
    clearTimeout(item.timer);
    const limits: Limits = {
      maxPhotos: config.maxPhotos ?? MAX_PHOTOS,
      maxPhotoBytes: config.maxPhotoBytes ?? MAX_PHOTO_BYTES,
      skipped: [],
    };
    let used = false;
    try {
      used = await collect(item, message.content, limits);
    } catch {
      log("[sidecar] could not read one message; skipped it");
    }
    for (const kind of limits.skipped) {
      log(`[sidecar] skipped a message type the check cannot read (${kind})`);
    }
    if (used) pending.set(space.id, item);
    if (pending.get(space.id) === item) {
      item.timer = setTimeout(() => flush(space.id), quietMs);
    }
  }
  // The stream ended (shutdown, or a test): check what is still waiting, then finish.
  for (const [id, item] of [...pending]) {
    clearTimeout(item.timer);
    flush(id);
  }
  await Promise.all(running);
}

type SpectrumModule = {
  Spectrum: (options: Record<string, unknown>) => Promise<PhotonApp>;
  imessage: { config: () => unknown };
};

async function loadSpectrum(): Promise<SpectrumModule> {
  const { Spectrum } = await import("spectrum-ts");
  const { imessage } = await import("spectrum-ts/providers/imessage");
  return { Spectrum, imessage } as unknown as SpectrumModule;
}

/** Connect to the Photon project in the env. The secret goes to the SDK and nowhere else. */
export async function connectPhoton(
  env: Record<string, string | undefined>,
  load: () => Promise<SpectrumModule> = loadSpectrum,
  log: Log = console.log,
): Promise<PhotonApp> {
  const projectId = env.SPECTRUM_PROJECT_ID;
  const projectSecret = env.SPECTRUM_PROJECT_SECRET;
  if (!projectId || !projectSecret) {
    throw new Error("Photon needs SPECTRUM_PROJECT_ID and SPECTRUM_PROJECT_SECRET in the env.");
  }
  const { Spectrum, imessage } = await load();
  // The SDK's own logger can print chat ids, which hold phone numbers: errors only, and no
  // telemetry leaves for Photon's collector.
  const app = await Spectrum({
    projectId,
    projectSecret,
    providers: [imessage.config()],
    options: { logLevel: "error" },
    telemetry: false,
  });
  log("[sidecar] connected to Photon (iMessage)");
  return app;
}

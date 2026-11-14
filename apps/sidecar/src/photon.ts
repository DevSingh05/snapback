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
  handleMessage,
  isAllowed,
  renterId,
  type InboundMessage,
  type SidecarConfig,
} from "./handler";
import { answerCommand, type WatchBook } from "./watch";

export type PhotonContent =
  | { type: "text"; text: string }
  | { type: "attachment"; mimeType: string; size?: number; read: () => Promise<Uint8Array> }
  | { type: "richlink"; url: string }
  // more than one part in one send (a caption and a photo), and a swipe-reply
  | { type: "group"; items: { content: PhotonContent }[] }
  | { type: "reply"; content: PhotonContent }
  | { type: string };

export type PhotonMessage = { direction: "inbound" | "outbound"; content: PhotonContent };

export type PhotonSpace = { id: string; send: (text: string) => Promise<unknown> };

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

type Pending = { space: PhotonSpace; texts: string[]; images: Blob[]; timer?: NodeJS.Timeout };

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

  const flush = (id: string) => {
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    const msg: InboundMessage = {
      threadId: id,
      text: item.texts.join("\n"),
      imageUrls: [],
      images: item.images,
      receivedAt: new Date().toISOString(),
    };
    // The client is bound to this space: it cannot send anywhere else.
    const client = {
      async reply(threadId: string, text: string) {
        if (threadId !== item.space.id) throw new Error("a reply may only go to its own thread");
        await item.space.send(text);
      },
    };
    running.push(
      handleMessage(msg, client, config).then(
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

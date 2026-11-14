/**
 * Photon (Spectrum, iMessage) for the sidecar (D4, #38): renter messages in, the card back out.
 *
 * Only the parts of `spectrum-ts` the sidecar uses are typed here, so the loop is tested with a
 * fake app and CI never needs an account. The SDK is loaded only when a project is configured.
 *
 * Hard rules, on top of handler.ts:
 * - SNAPBACK never texts first. The only send is `space.send`, on the space an inbound message
 *   came from, after that message. Outbound messages (our own echoes) are skipped.
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

export type PhotonContent =
  | { type: "text"; text: string }
  | { type: "attachment"; mimeType: string; read: () => Promise<Uint8Array> }
  | { type: "richlink"; url: string }
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
};

type Log = (line: string) => void;

const QUIET_MS = 4000;

type Pending = { space: PhotonSpace; texts: string[]; images: Blob[]; timer?: NodeJS.Timeout };

/** Read one inbound message into the pending check for its space. False if nothing usable. */
async function collect(pending: Pending, message: PhotonMessage): Promise<boolean> {
  const content = message.content;
  if (content.type === "text" && "text" in content) {
    pending.texts.push(content.text);
    return true;
  }
  if (content.type === "richlink" && "url" in content) {
    pending.texts.push(content.url);
    return true;
  }
  if (content.type === "attachment" && "read" in content && content.mimeType.startsWith("image/")) {
    const bytes = await content.read();
    pending.images.push(new Blob([new Uint8Array(bytes)], { type: content.mimeType }));
    return true;
  }
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
    const item = pending.get(space.id) ?? { space, texts: [], images: [] };
    try {
      if (!(await collect(item, message))) continue;
    } catch {
      log("[sidecar] could not read one message; skipped it");
      continue;
    }
    pending.set(space.id, item);
    clearTimeout(item.timer);
    item.timer = setTimeout(() => flush(space.id), quietMs);
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
  const app = await Spectrum({ projectId, projectSecret, providers: [imessage.config()] });
  log("[sidecar] connected to Photon (iMessage)");
  return app;
}

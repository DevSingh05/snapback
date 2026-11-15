/**
 * Intake sidecar: bridges inbound renter iMessages to the API (module 8, D4).
 *
 * The message logic is in handler.ts; Photon (Spectrum, iMessage) is in photon.ts. Both are
 * tested with fakes, so CI needs no account.
 * Hard rule: outbound messages only go back to the renter's own thread. We never message the
 * person who posted a listing. SNAPBACK texts first only in a thread that linked a Finder
 * watch (ruling R-M1, M10, watch.ts): at most 3 a day, and a stop word ends it.
 *
 * Env (read from the shell, then the repo's local .env, which is git-ignored):
 * API_URL, WEB_URL, SIDECAR_ALLOWED_THREADS (comma-separated thread ids, or their keyed hashes
 * `imsg-...` as logged for a thread that is not allowed; empty answers nobody),
 * SIDECAR_RENTER_SALT (keys the renter id hash; set it so ids, and daily limits, survive a
 * restart), SPECTRUM_PROJECT_ID and SPECTRUM_PROJECT_SECRET (Photon; without both the sidecar
 * only logs, which is the CI and fixture path).
 */

import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

import { CaseMemory, type MessageClient } from "./handler";
import { connectPhoton, publicWebUrl, runPhoton, stageOptions } from "./photon";
import { WatchBook, pushEvents, readEvents } from "./watch";

try {
  process.loadEnvFile(fileURLToPath(new URL("../../../.env", import.meta.url)));
} catch {
  // no local .env: the shell's env is used as it is
}

export { handleMessage, type InboundMessage } from "./handler";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const allowed = (process.env.SIDECAR_ALLOWED_THREADS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/** Keys the renter id hash. Without the env value, a per-process salt (ids change on restart). */
export const renterSalt = process.env.SIDECAR_RENTER_SALT || randomBytes(32).toString("hex");
if (!process.env.SIDECAR_RENTER_SALT) {
  console.warn("[sidecar] SIDECAR_RENTER_SALT is not set; renter ids will change on restart.");
}

export async function apiIsUp(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/healthz`);
    return res.ok;
  } catch {
    return false;
  }
}

/** The CI and fixture path, when no Photon project is configured: logs instead of sending. */
export const logOnlyClient: MessageClient = {
  async reply(_threadId, text) {
    console.log(`[sidecar] would reply (${text.length} chars) to an allowed thread`);
  },
};

const photon = Boolean(process.env.SPECTRUM_PROJECT_ID && process.env.SPECTRUM_PROJECT_SECRET);
const up = await apiIsUp();
console.log(
  `[sidecar] API at ${API_URL} is ${up ? "up" : "not reachable"}. ` +
    `${allowed.length} allowed thread(s). ` +
    (photon ? "Photon: connecting." : "Photon is not configured: log only."),
);

if (photon) {
  const webUrl = publicWebUrl(process.env); // a renter's phone cannot open localhost
  const maxPhotoMb = Number(process.env.SNAPBACK_MAX_PHOTO_MB) || 10;
  const app = await connectPhoton(process.env);
  const stop = () => void app.stop?.().finally(() => process.exit(0));
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  const watches = new WatchBook();
  const eventsToken = process.env.SNAPBACK_EVENTS_TOKEN;
  if (eventsToken) {
    // Watch alerts (M10): follow the API's events stream and reconnect when it ends, from
    // the last event seen (Last-Event-ID), so a reconnect never texts the same match again.
    void (async () => {
      let lastId: string | undefined;
      const seen = (id: string) => void (lastId = id);
      for (;;) {
        try {
          const events = readEvents(API_URL, eventsToken, fetch, lastId);
          await pushEvents(events, watches, webUrl, console.log, seen);
        } catch {
          console.log("[sidecar] events stream closed; reconnecting");
        }
        await new Promise((done) => setTimeout(done, 5000));
      }
    })();
  } else {
    console.log("[sidecar] SNAPBACK_EVENTS_TOKEN is not set: watch alerts will not be sent.");
  }
  // Voice replies (Best Voice Agent): the SDK's own builder sends a native voice memo bubble.
  const { voice, attachment } = await import("spectrum-ts");
  const stage = stageOptions(process.env);
  await runPhoton(app, {
    makeVoice: (bytes: Uint8Array, mimeType: string) => voice(Buffer.from(bytes), { mimeType }),
    // the card picture and the "checking" reply can each be turned off on stage
    ...(stage.sendCardImage
      ? {
          makeImage: (bytes: Uint8Array, mimeType: string) =>
            attachment(Buffer.from(bytes), { mimeType, name: "snapback-card.png" }),
        }
      : {}),
    memory: new CaseMemory(),
    acknowledge: stage.acknowledge,
    watches,
    apiUrl: API_URL,
    webUrl,
    allowedThreads: new Set(allowed),
    renterSalt,
    maxPhotoBytes: maxPhotoMb * 1024 * 1024,
  });
}

/**
 * Intake sidecar: bridges inbound renter iMessages to the API (module 8, D4).
 *
 * The message logic is in handler.ts and is tested with a mocked client. Photon itself is not
 * wired yet: it needs an account and keys, which a human sets up (D4 is `human-needed`).
 * Hard rule: outbound messages only go back to the renter's own thread. We never message the
 * person who posted a listing, and SNAPBACK never texts first.
 *
 * Env: API_URL, WEB_URL, SIDECAR_ALLOWED_THREADS (comma-separated thread ids; empty answers
 * nobody), SIDECAR_RENTER_SALT (keys the renter id hash; set it so ids, and daily limits, survive
 * a restart).
 */

import { randomBytes } from "node:crypto";

import { type MessageClient } from "./handler";

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

/** Placeholder until Photon is wired: logs instead of sending. */
export const logOnlyClient: MessageClient = {
  async reply(_threadId, text) {
    console.log(`[sidecar] would reply (${text.length} chars) to an allowed thread`);
  },
};

const up = await apiIsUp();
console.log(
  `[sidecar] API at ${API_URL} is ${up ? "up" : "not reachable"}. ` +
    `${allowed.length} allowed thread(s). Photon is not wired yet.`,
);

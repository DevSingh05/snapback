/**
 * Intake sidecar: bridges inbound renter messages to the API.
 *
 * Stub only. Photon is not wired yet; the data + intake lane owns this file.
 * Hard rule: outbound messages may only go back to the renter's own thread.
 * We never message the person who posted a listing.
 */

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/** One inbound message from a renter, whatever channel it arrived on. */
export type InboundMessage = {
  threadId: string;
  text?: string;
  imageUrls: string[];
  receivedAt: string;
};

export async function apiIsUp(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/healthz`);
    return res.ok;
  } catch {
    return false;
  }
}

const up = await apiIsUp();
console.log(
  `[sidecar] stub running. API at ${API_URL} is ${up ? "up" : "not reachable"}. Photon is not wired yet.`,
);

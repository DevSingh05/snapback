export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 10;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
const IMAGE_EXT = /\.(jpe?g|png|webp|heic|heif)$/i;

export type LinkResult = { ok: true; url: string } | { ok: false; error: string };

const LINK_HELP =
  "That does not look like a web address. Paste the full address of the listing, for example https://www.zillow.com/homedetails/123.";

const TLDS = new Set([
  "com",
  "org",
  "net",
  "edu",
  "gov",
  "io",
  "co",
  "us",
  "app",
  "info",
  "biz",
  "me",
  "ly",
  "homes",
  "rent",
  "realty",
  "apartments",
  "uk",
  "ca",
]);

// The host part of a scheme-less token, e.g. "craigslist.org" from "craigslist.org/apa/1".
function bareHost(text: string): string {
  const afterAt = text.includes("@") ? text.slice(text.lastIndexOf("@") + 1) : text;
  return (afterAt.split(/[/?#:]/)[0] ?? "").toLowerCase();
}

function hasKnownTld(text: string): boolean {
  const host = bareHost(text);
  const tld = host.split(".").pop() ?? "";
  return host.includes(".") && TLDS.has(tld);
}

export function validateLink(raw: string): LinkResult {
  const text = raw.trim();
  if (!text || /\s/.test(text)) return { ok: false, error: LINK_HELP };
  const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(text);
  if (!scheme && /^[a-z][a-z0-9+.-]*:/i.test(text) && !/^[^/]*\.[a-z]+:\d+/i.test(text)) {
    return { ok: false, error: LINK_HELP };
  }
  if (scheme && !/^https?$/i.test(scheme[1] ?? "")) {
    return { ok: false, error: LINK_HELP };
  }
  if (!scheme && !hasKnownTld(text)) return { ok: false, error: LINK_HELP };
  const withScheme = scheme ? text : `https://${text}`;
  let url: URL;
  try {
    url = new URL(withScheme);
  } catch {
    return { ok: false, error: LINK_HELP };
  }
  if (url.username || url.password) {
    return {
      ok: false,
      error:
        "That looks like an email address, not a listing link. Paste the address of the listing page instead.",
    };
  }
  const host = url.hostname;
  if (!host.includes(".") || host.startsWith(".") || host.endsWith(".")) {
    return { ok: false, error: LINK_HELP };
  }
  return { ok: true, url: withScheme };
}

export type ListingText = { kind: "link" | "text" | "empty" };

// One box takes either a link or pasted listing text. A single token with an http(s) scheme,
// an at sign, or a host ending in a known TLD is a link; "1.5BR" and longer text are listing text.
export function classifyListingText(raw: string): ListingText {
  const text = raw.trim();
  if (!text) return { kind: "empty" };
  if (!/\s/.test(text) && (/^https?:/i.test(text) || text.includes("@") || hasKnownTld(text))) {
    return { kind: "link" };
  }
  return { kind: "text" };
}

function isImage(f: File): boolean {
  return IMAGE_TYPES.includes(f.type.toLowerCase()) || (f.type === "" && IMAGE_EXT.test(f.name));
}

export function addFiles(existing: File[], incoming: File[]): { files: File[]; errors: string[] } {
  const files = [...existing];
  const errors: string[] = [];
  let overflow = false;
  for (const f of incoming) {
    if (!isImage(f)) {
      errors.push(
        `${f.name} is not a photo. Use a screenshot or photo (JPG, PNG, WebP or HEIC), not a PDF or document.`,
      );
      continue;
    }
    if (f.size > MAX_FILE_BYTES) {
      errors.push(
        `${f.name} is larger than 10 MB. Take a screenshot of it instead, or pick a smaller photo.`,
      );
      continue;
    }
    if (files.some((g) => g.name === f.name && g.size === f.size)) continue;
    if (files.length >= MAX_FILES) {
      overflow = true;
      continue;
    }
    files.push(f);
  }
  if (overflow) errors.push(`You can add up to ${MAX_FILES} photos. Remove one to add another.`);
  return { files, errors };
}

export type SubmissionResult =
  | { ok: true; link: string | null; text: string | null; files: File[] }
  | { ok: false; error: string };

export function validateSubmission(input: { text: string; files: File[] }): SubmissionResult {
  const kind = classifyListingText(input.text).kind;
  if (kind === "empty" && input.files.length === 0) {
    return { ok: false, error: "Paste a listing link or add screenshots of the listing to start." };
  }
  if (kind === "link") {
    const r = validateLink(input.text);
    if (!r.ok) return r;
    return { ok: true, link: r.url, text: null, files: input.files };
  }
  return {
    ok: true,
    link: null,
    text: kind === "text" ? input.text.trim() : null,
    files: input.files,
  };
}

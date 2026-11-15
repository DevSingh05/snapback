/**
 * Adaptive memory (D2, night plan on #11): SNAPBACK learns a renter from what they say.
 *
 * - Kept per renter under the keyed hash `renterId(threadId, salt)`, never a phone number or a
 *   handle, for PROFILE_TTL_MS (30 days) after the last thing learned.
 * - Learned only from the renter's own words about themselves: their language, the city they
 *   are moving to or looking in, their budget ("my budget is", "I can pay up to") and the beds
 *   they need ("I need 2 beds"). An ad's own rent, beds or city is never taken for theirs.
 * - "what do you remember?" lists it; "forget me" wipes it at once, in memory and on disk.
 * - Never logged. Saved, when a file is given, under the git-ignored `data/` folder (purged by
 *   `make purge`), holding only the hash and the learned fields.
 */

import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const PROFILE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

export type Lang = "en" | "es";
export type Profile = { lang?: Lang; city?: string; budget?: number; beds?: number };
type Stored = Profile & { at: number };

const ES_WORDS =
  /\b(hola|busco|necesito|quiero|renta|rentar|alquiler|departamento|apartamento|recámaras?|recamaras?|habitaciones?|depósito|deposito|dueño|gracias|por favor|cuánto|cuanto|presupuesto|mes|casa|es real|estafa|vivienda)\b/gi;
const EN_WORDS =
  /\b(the|is|this|and|for|my|i|i'm|want|need|looking|rent|real|apartment|house|please)\b/gi;
const CITIES = [
  "Houston",
  "Dallas",
  "Austin",
  "San Antonio",
  "Fort Worth",
  "El Paso",
  "New York",
  "Chicago",
  "Los Angeles",
  "Philadelphia",
  "Princeton",
];

function money(raw: string): number | undefined {
  const n = Number(raw.replace(/[,$\s]/g, ""));
  return Number.isFinite(n) && n >= 200 && n <= 50_000 ? n : undefined;
}

/** What a message says about the renter themselves. Only fields it actually states are set. */
export function learnFrom(text: string): Profile {
  const said = text.slice(0, 500);
  const out: Profile = {};
  if (/[¿¡ñ]/i.test(said) || (said.match(ES_WORDS)?.length ?? 0) >= 2) out.lang = "es";
  else if ((said.match(EN_WORDS)?.length ?? 0) >= 2) out.lang = "en";

  const budget =
    /\b(?:my budget(?: is)?|budget of|i can (?:afford|pay)(?: up to)?|i can spend(?: up to)?|mi presupuesto(?: es)?|puedo pagar(?: hasta)?)\s*(?:about|around|is|of|hasta)?\s*(\$?\s?\d{1,2},?\d{3}|\$?\s?\d{3,5})/i.exec(
      said,
    );
  const amount = budget?.[1] ? money(budget[1]) : undefined;
  if (amount !== undefined) out.budget = amount;

  const beds =
    /\b(?:i need|i want|looking for|need|busco|necesito|quiero)\b[^.!?\n]{0,30}?\b(\d{1,2})\s*(?:-|\s)?(?:beds?|bedrooms?|br|bd|recámaras?|recamaras?|habitaciones?|cuartos?)\b/i.exec(
      said,
    );
  if (beds?.[1]) out.beds = Number(beds[1]);

  for (const city of CITIES) {
    const where = new RegExp(
      String.raw`\b(?:moving to|move to|relocating to|looking in|looking for a place in|living in|me mudo a|busco en|en)\s+${city}\b`,
      "i",
    );
    if (where.test(said)) {
      out.city = city;
      break;
    }
  }
  return out;
}

/** The profiles, keyed by the keyed hash. In memory, mirrored to `file` when one is given. */
export class ProfileStore {
  private all = new Map<string, Stored>();

  constructor(
    private file?: string,
    private now: () => number = Date.now,
  ) {
    if (!file) return;
    try {
      const saved = JSON.parse(readFileSync(file, "utf8")) as Record<string, Stored>;
      for (const [key, value] of Object.entries(saved)) this.all.set(key, value);
    } catch {
      // no file yet, or one we cannot read: start empty
    }
  }

  /** The renter's profile if still fresh (expired ones are dropped), else null. */
  get(key: string): Profile | null {
    const found = this.all.get(key);
    if (!found) return null;
    if (this.now() - found.at > PROFILE_TTL_MS) {
      this.all.delete(key);
      this.save();
      return null;
    }
    const profile: Profile = {};
    if (found.lang) profile.lang = found.lang;
    if (found.city) profile.city = found.city;
    if (found.budget !== undefined) profile.budget = found.budget;
    if (found.beds !== undefined) profile.beds = found.beds;
    return Object.keys(profile).length ? profile : null;
  }

  /** Merge what this message says about the renter. Returns the profile after. */
  learn(key: string, text: string): Profile {
    const learned = learnFrom(text);
    const before = this.get(key) ?? {};
    if (Object.keys(learned).length === 0) return before;
    const after = { ...before, ...learned };
    this.all.set(key, { ...after, at: this.now() });
    this.save();
    return after;
  }

  forget(key: string): void {
    this.all.delete(key);
    this.save();
  }

  private save(): void {
    if (!this.file) return;
    try {
      mkdirSync(dirname(this.file), { recursive: true });
      const tmp = `${this.file}.tmp`;
      writeFileSync(tmp, JSON.stringify(Object.fromEntries(this.all)), { mode: 0o600 });
      renameSync(tmp, this.file);
    } catch {
      // the profile is a convenience: a failed write never breaks a reply
    }
  }
}

const REMEMBER =
  /^\s*(what do you (remember|know)( about me)?|what have you (saved|kept)|¿?qu[ée] (recuerdas|sabes)( de m[ií])?\??)\s*[?.!]*\s*$/i;
const FORGET =
  /^\s*(forget me|forget everything|delete my (data|info)|olv[ií]dame|borra mis datos)\s*[.!]*\s*$/i;

function listed(profile: Profile, lang: Lang): string[] {
  const es = lang === "es";
  const lines: string[] = [];
  if (profile.budget !== undefined) {
    lines.push(`${es ? "presupuesto" : "budget"}: $${profile.budget.toLocaleString("en-US")}`);
  }
  if (profile.beds !== undefined) lines.push(`${es ? "recámaras" : "beds"}: ${profile.beds}`);
  if (profile.city) lines.push(`${es ? "ciudad" : "city"}: ${profile.city}`);
  if (profile.lang)
    lines.push(`${es ? "idioma" : "language"}: ${profile.lang === "es" ? "español" : "English"}`);
  return lines;
}

/** The reply to "what do you remember?" or "forget me", or null when it is neither. */
export function profileCommand(text: string, key: string, store: ProfileStore): string | null {
  const spanish = /[¿¡]|olv[ií]dame|recuerdas|borra/i.test(text);
  if (FORGET.test(text)) {
    store.forget(key);
    return spanish
      ? "Listo, olvidé todo lo que sabía de usted."
      : "Done. I forgot everything I knew about you.";
  }
  if (!REMEMBER.test(text)) return null;
  const profile = store.get(key);
  const lang: Lang = profile?.lang ?? (spanish ? "es" : "en");
  const lines = profile ? listed(profile, lang) : [];
  if (lines.length === 0) {
    return lang === "es"
      ? "No guardo nada de usted. Si me dice su presupuesto o cuántas recámaras necesita, lo recordaré 30 días."
      : "Nothing saved about you yet. Tell me your budget or how many beds you need and I'll remember it for 30 days.";
  }
  return lang === "es"
    ? [
        "Esto es lo que recuerdo (30 días):",
        ...lines.map((l) => `- ${l}`),
        "",
        'Escriba "olvídame" para borrarlo.',
      ].join("\n")
    : [
        "Here's what I remember (for 30 days):",
        ...lines.map((l) => `- ${l}`),
        "",
        'Text "forget me" to delete it.',
      ].join("\n");
}

/**
 * D5 (#11, Vidyut 20:33): "how did you check?" in iMessage, from the case's own timeline
 * (GET /cases/{id}/timeline, #267, read token in a header).
 *
 * One short line per agent, in the timeline's own words (Rules, Record, Phone, Photo), red flags
 * from the card first, then the verdict line. Never a phone digit and never a rent figure: a
 * step result that carries either is dropped and only its label is kept. No case is ever made.
 */

import { checkAnchor, MAX_FLAG_LINKS } from "./anchors";
import type { Lang } from "./profile";

export type TimelineStep = { label: string; result: string; by?: string };
export type Timeline = { source?: string; steps: TimelineStep[] };
type CardLine = { label: string; text: string; tone: string };
type CardLike = {
  source: string;
  state: string;
  headline?: string;
  rows: { lines: CardLine[] }[];
  does_not?: string[] | null;
};

type Agent = "rules" | "record" | "phone" | "photo";

const NAMES: Record<Lang, Record<Agent | "result" | "flag" | "title" | "full", string>> = {
  en: {
    rules: "Rules agent",
    record: "Record agent",
    phone: "Phone agent",
    photo: "Photo agent",
    result: "Result",
    flag: "Red flag",
    title: "How I checked",
    full: "Full report:",
  },
  es: {
    rules: "Agente de reglas",
    record: "Agente de registro",
    phone: "Agente de teléfono",
    photo: "Agente de fotos",
    result: "Resultado",
    flag: "Alerta",
    title: "Cómo lo revisé",
    full: "Informe completo:",
  },
};

const VERDICT = /worked out the result|calcul[oó] el resultado/i;
// "The deep agent stopped: <reason>; code set the verdict" (timeline.fallback): its own line
const FALLBACK = /agent(?:e)? (?:profundo )?(?:stopped|se detuvo)/i;
// The only step results shown: the known timeline.result.* strings (src/snapback/card/strings.py).
// Anything else is trace text ("Plan A: 457 inliers vs 9", "Only one option was open"), so only
// the step's label is kept.
const KNOWN_RESULTS = new Set([
  "Read what the ad says it is.",
  "Inside the range on record.",
  "Below the range on record.",
  "No rent on record to compare.",
  "It is the office's number.",
  "It is not the office's number.",
  "Leyó lo que el anuncio dice que es.",
  "Dentro del rango registrado.",
  "Por debajo del rango registrado.",
  "No hay renta registrada para comparar.",
  "Es el número de la oficina.",
  "No es el número de la oficina.",
]);
const META =
  /wrote its plan|working note|waited|handed the|sub-agent|chose which checks|drew a random spot|code used its own pick|escribi[oó] su plan|nota de trabajo|esper[oó]|entreg[oó]|subagente/i;
// order matters: the ad's own words first, then phone, then the record (rent mentions floor
// plans), then photos
const AGENT_OF: [Agent, RegExp][] = [
  // a license step names "the ad" too ("Looked up the license the ad names"): the record's
  ["record", /licen[cs]e|licencia/i],
  ["rules", /\bthe ad\b|ad's|claims|anuncio|reclamos/i],
  ["phone", /phone|leasing office|tel[eé]fono|oficina/i],
  [
    "record",
    /record|rent|owner|license|for-sale|for sale|registro|renta|propietario|licencia|venta/i,
  ],
  ["photo", /photo|scan|floor plan|foto|escaneo|plano/i],
];

const PHONE = /\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}|\b\d{3}[-.\s]\d{4}\b/;
const MONEY = /\$\s?\d|\b\d{1,3},\d{3}\b/;

/** A step as "label: result" when the result is a known plain string, else the label alone.
 * A label with a phone number or a rent is never shown. */
function said(step: TimelineStep): string {
  const label = step.label.trim();
  if (PHONE.test(label) || MONEY.test(label)) return "";
  const result = (step.result ?? "").trim();
  return KNOWN_RESULTS.has(result) ? `${label}: ${result}` : label;
}

function clean(line: string): string {
  return PHONE.test(line) || MONEY.test(line) ? "" : line;
}

/** The reply to "how did you check?". `headline` is the card's own (locked) headline. */
export function howCheckedText(
  timeline: Timeline,
  card: CardLike,
  link: string,
  lang: Lang = "en",
  headline?: string,
): string {
  const n = NAMES[lang];
  const source = (timeline.source ?? card.source ?? "").toUpperCase();
  const top = headline ?? card.headline ?? defaultHeadline(card.state, lang);
  const lines = [top, "", `${n.title} (${source}):`];

  // XO 03:32: a red flag links to its line on the web card when that card lists it (English).
  const onCard = new Set((card.does_not ?? []).map(checkAnchor).filter(Boolean));
  let linked = 0;
  for (const row of card.rows) {
    for (const line of row.lines) {
      if (line.tone !== "red_flag") continue;
      const text = clean(`${line.label}: ${line.text}`);
      if (!text) continue;
      const anchor = lang === "en" ? checkAnchor(text) : null;
      if (anchor && onCard.has(anchor) && linked < MAX_FLAG_LINKS) {
        linked += 1;
        lines.push(`- ${n.flag}: ${text} ${link}#${anchor}`);
      } else {
        lines.push(`- ${n.flag}: ${text}`);
      }
    }
  }

  const byAgent = new Map<Agent, string[]>();
  let fellBack = "";
  for (const step of timeline.steps) {
    // the verdict is the card's own headline, never a step's text (that step only exists once
    // the case is done, and says how, not what)
    if (VERDICT.test(step.label)) continue;
    if (FALLBACK.test(step.label)) {
      fellBack = clean(step.label.trim());
      continue;
    }
    if (META.test(step.label)) continue;
    const agent = AGENT_OF.find(([, pattern]) => pattern.test(step.label))?.[0];
    const text = said(step);
    if (!agent || !text) continue;
    byAgent.set(agent, [...(byAgent.get(agent) ?? []), text]);
  }
  for (const agent of ["rules", "record", "phone", "photo"] as const) {
    const parts = byAgent.get(agent);
    if (parts?.length) lines.push(`- ${n[agent]}: ${parts.join("; ")}`);
  }
  if (fellBack) lines.push(`- ${fellBack}`);
  lines.push(`- ${n.result}: ${top}`);
  lines.push("", `${n.full} ${link}`);
  return lines.join("\n");
}

const DEFAULT: Record<Lang, Record<string, string>> = {
  en: {
    hold: "Hold off for now",
    unverified: "Could not place these photos",
    dont_pay: "Don't pay. Something here doesn't match.",
    verified: "Checks passed. Still follow the two rules.",
  },
  es: {
    hold: "Espere por ahora",
    unverified: "No se pudieron ubicar estas fotos",
    dont_pay: "No pague. Algo aquí no coincide.",
    verified: "Las revisiones pasaron. Siga igual las dos reglas.",
  },
};

function defaultHeadline(state: string, lang: Lang): string {
  return DEFAULT[lang][state] ?? DEFAULT[lang].hold ?? "Hold off for now";
}

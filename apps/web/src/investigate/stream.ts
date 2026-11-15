// The 90-day stream view's data and arithmetic. The data is `fixtures/forensics/stream_timeline.json`
// (made by `snapback.forensics.detect`; also served at GET /forensics/stream). All of it is
// SYNTHETIC. Days in the file count from 0; the screen counts from 1 (`dayNo`), so slider
// position 0 is the empty board and position 90 shows all 90 days.

export type SignalKind = "phone" | "photo" | "wording" | "site";

export interface StreamAd {
  id: number;
  day: number;
  flag_day: number;
  phone: string;
  hood: string;
  rent: number;
}

export interface StreamSignal {
  kind: SignalKind;
  key: string;
  label: string;
  weight: number;
  n_ads: number;
  ad_ids: number[];
}

export interface KindCount {
  values: number;
  ads: number;
  weight: number;
}

export interface Detection {
  first_day: number;
  flag_day: number | null;
  gap_days: number | null;
  ads_before_flag: number;
  ad_days_before_flag: number;
  renters_est: number;
}

export interface StreamGroup extends Detection {
  id: string;
  label: string;
  n_ads: number;
  n_phones: number;
  score: number;
  ads: StreamAd[];
  signals: StreamSignal[];
  by_kind: Partial<Record<SignalKind, KindCount>>;
  findings: { kind: string; title: string; summary: string; score: number }[];
  answer_key: Record<string, number>;
}

export interface SeededRing extends Detection {
  name: string;
  n_ads: number;
  flagged_ads: number;
  separated: boolean;
}

export interface StreamTimeline {
  label: string;
  synthetic: boolean;
  source: string;
  seed: number;
  start: string;
  days: number;
  n_ads: number;
  min_ads: number;
  views_per_ad_day: number;
  weights: Record<SignalKind, number>;
  groups: StreamGroup[];
  other_ads_by_day: number[];
  flagged_ads_by_day: number[];
  groups_by_day: number[];
  summary: {
    groups_found: number;
    median_gap_days: number | null;
    n_gap: number;
    renters_est: number;
  };
  answer_key: {
    n_seeded: number;
    seeded_flagged: number;
    seeded_separated: number;
    median_gap_days: number | null;
    n_gap: number;
    ring_ads: number;
    ring_ads_flagged: number;
    honest_flagged: number;
    n_honest: number;
    seeded: SeededRing[];
  };
}

export const KINDS: SignalKind[] = ["phone", "photo", "wording", "site"];

export const KIND_NAME: Record<SignalKind, string> = {
  phone: "Same phone number",
  photo: "Same photos, re-cropped",
  wording: "Same pay-first wording, reworded",
  site: "Same site named in the ad",
};

export const KIND_UNIT: Record<SignalKind, string> = {
  phone: "numbers",
  photo: "photo-sets",
  wording: "wordings",
  site: "sites",
};

// ---- the slider ---------------------------------------------------------------------------

/** A zero-based day from the file, as the day number the screen shows. */
export function dayNo(index: number): number {
  return index + 1;
}

export function clampDay(value: number, days: number): number {
  if (!Number.isFinite(value)) return days;
  return Math.min(days, Math.max(0, Math.round(value)));
}

/** One tick of Play: the next position and whether to keep playing. It stops on the last day. */
export function stepDay(pos: number, days: number): { pos: number; playing: boolean } {
  const next = Math.min(days, pos + 1);
  return { pos: next, playing: next < days };
}

/** Where Play starts from: the current position, or the empty board when it is at the end. */
export function playFrom(pos: number, days: number): number {
  return pos >= days ? 0 : pos;
}

/** `?day=45&ring=B` opens the view on that day with that group selected. */
export function readQuery(
  search: string,
  data: StreamTimeline,
): { pos: number; ring: string | null } {
  const q = new URLSearchParams(search);
  const day = q.get("day");
  const ring = (q.get("ring") ?? "").toUpperCase();
  return {
    pos: day === null || day.trim() === "" ? data.days : clampDay(Number(day), data.days),
    ring: data.groups.some((g) => g.id === ring) ? ring : null,
  };
}

export function dateOf(start: string, pos: number): string {
  const d = new Date(`${start}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + Math.max(0, pos - 1));
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function isoOf(start: string, index: number): string {
  const d = new Date(`${start}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + index);
  return d.toISOString().slice(0, 10);
}

export interface GroupFrame {
  id: string;
  shown: number; // ads posted by this position
  linked: number; // of those, ads the finder has put in a group by this position
  flagged: boolean;
  started: boolean;
}

export interface Frame {
  pos: number;
  adsPosted: number;
  adsFlagged: number;
  groupsFlagged: number;
  seededFlagged: number;
  groups: GroupFrame[];
}

/** Everything the screen shows at slider position `pos`: an ad posted on zero-based day d is on
 * the board from position d + 1, and a flag raised on day f shows from position f + 1. */
export function frameAt(data: StreamTimeline, pos: number): Frame {
  const p = clampDay(pos, data.days);
  const groups = data.groups.map((g) => {
    const shown = g.ads.filter((a) => a.day < p);
    return {
      id: g.id,
      shown: shown.length,
      linked: shown.filter((a) => a.flag_day < p).length,
      flagged: g.flag_day !== null && g.flag_day < p,
      started: g.first_day < p,
    };
  });
  const other = data.other_ads_by_day.slice(0, p).reduce((s, n) => s + n, 0);
  return {
    pos: p,
    adsPosted: other + groups.reduce((s, g) => s + g.shown, 0),
    adsFlagged: p === 0 ? 0 : (data.flagged_ads_by_day[p - 1] ?? 0),
    groupsFlagged: groups.filter((g) => g.flagged).length,
    seededFlagged: data.answer_key.seeded.filter((r) => r.flag_day !== null && r.flag_day < p)
      .length,
    groups,
  };
}

// ---- links and signals ----------------------------------------------------------------------

export interface Link {
  kind: SignalKind;
  key: string;
  from: number;
  to: number;
  day: number; // the zero-based day the later ad was posted: when the link exists
}

/** A shared value joins each ad to the one before it that carries the same value: a chain, so
 * a number on five ads draws four links, and each link appears with its later ad. */
export function linksOf(group: StreamGroup): Link[] {
  const dayOf = new Map(group.ads.map((a) => [a.id, a.day]));
  const out: Link[] = [];
  for (const s of group.signals) {
    s.ad_ids.slice(1).forEach((to, i) => {
      out.push({ kind: s.kind, key: s.key, from: s.ad_ids[i] ?? to, to, day: dayOf.get(to) ?? 0 });
    });
  }
  return out;
}

export interface SignalRow extends KindCount {
  kind: SignalKind;
  top: { key: string; label: string; n: number }[];
}

/** The evidence panel's rows at position `pos`: per kind, how many shared values link how many
 * different ads, counting only ads already posted. At the last day it equals the backend's
 * `by_kind` for the group. */
export function signalRows(group: StreamGroup, pos: number): SignalRow[] {
  const posted = new Set(group.ads.filter((a) => a.day < pos).map((a) => a.id));
  const rows: SignalRow[] = [];
  for (const kind of KINDS) {
    const live = group.signals
      .filter((s) => s.kind === kind)
      .map((s) => ({ s, ids: s.ad_ids.filter((id) => posted.has(id)) }))
      .filter((x) => x.ids.length >= 2);
    if (!live.length) continue;
    rows.push({
      kind,
      values: live.length,
      ads: new Set(live.flatMap((x) => x.ids)).size,
      weight: live[0]?.s.weight ?? 0,
      top: live
        .map((x) => ({ key: x.s.key, label: x.s.label, n: x.ids.length }))
        .sort((a, b) => b.n - a.n || a.key.localeCompare(b.key)),
    });
  }
  return rows;
}

// ---- where things sit ---------------------------------------------------------------------

export interface Point {
  x: number;
  y: number;
}

export interface StageLayout {
  width: number;
  height: number;
  centres: Map<string, Point>;
  ads: Map<number, Point>;
}

const GOLDEN = 2.399963229728653;
const SPACING = 11;

/** Each group gets a cell of a grid; its ads sit on a sunflower spiral in posting order, so the
 * group grows outward as it posts. Deterministic: the same data draws the same picture. */
export function layoutStream(data: StreamTimeline, narrow: boolean): StageLayout {
  const width = narrow ? 620 : 1000;
  const cols = narrow ? 2 : 3;
  const rows = Math.max(1, Math.ceil(data.groups.length / cols));
  const cellH = narrow ? 300 : 326;
  const height = rows * cellH;
  const centres = new Map<string, Point>();
  const ads = new Map<number, Point>();
  data.groups.forEach((g, i) => {
    const c = {
      x: ((i % cols) + 0.5) * (width / cols),
      y: (Math.floor(i / cols) + 0.5) * cellH + 12,
    };
    centres.set(g.id, c);
    g.ads.forEach((ad, k) => {
      const r = SPACING * Math.sqrt(k + 0.6);
      ads.set(ad.id, { x: c.x + r * Math.cos(k * GOLDEN), y: c.y + r * Math.sin(k * GOLDEN) });
    });
  });
  return { width, height, centres, ads };
}

export function groupRadius(nAds: number): number {
  return SPACING * Math.sqrt(nAds + 0.6) + 12;
}

function mulberry(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The ads no group holds, as dots: one per ad, scattered by a seeded generator, per day. */
export function otherDots(data: StreamTimeline, width: number, height: number): Point[][] {
  const rand = mulberry(data.seed);
  return data.other_ads_by_day.map((n) =>
    Array.from({ length: n }, () => ({
      x: Math.round((6 + rand() * (width - 12)) * 10) / 10,
      y: Math.round((6 + rand() * (height - 12)) * 10) / 10,
    })),
  );
}

// ---- the case file ----------------------------------------------------------------------------

export interface CaseFile {
  case_file_version: 1;
  label: string;
  source: string;
  synthetic: true;
  notice: string;
  stream: { seed: number; first_day: string; days: number; n_ads: number };
  as_of_day: number;
  group: { id: string; label: string; n_ads: number; n_ads_as_of_day: number; n_phones: number };
  detection: {
    first_ad_day: number;
    first_ad_date: string;
    flagged_day: number | null;
    flagged_date: string | null;
    days_to_detect: number | null;
    ads_up_before_flag: number;
    ad_days_before_flag: number;
    renters_estimate: number;
    renters_estimate_basis: string;
  };
  method: string;
  signals: {
    kind: SignalKind;
    name: string;
    weight: number;
    shared_values: number;
    ads_linked: number;
    values: { key: string; label: string; ad_ids: number[] }[];
  }[];
  findings: StreamGroup["findings"];
  answer_key_check: Record<string, number>;
  ads: { id: number; day: number; date: string; phone: string; area: string; rent: number }[];
}

/** What an investigator hands on: the group as of day 90, why its ads are linked, and when. */
export function caseFile(data: StreamTimeline, group: StreamGroup, pos: number): CaseFile {
  const rows = signalRows(group, data.days);
  return {
    case_file_version: 1,
    label: data.label,
    source: data.source,
    synthetic: true,
    notice:
      "SYNTHETIC DATA. Every ad, number, photo id and site here was generated for a demo. " +
      "No real person, place, phone number or site is in it.",
    stream: { seed: data.seed, first_day: data.start, days: data.days, n_ads: data.n_ads },
    as_of_day: pos,
    group: {
      id: group.id,
      label: group.label,
      n_ads: group.n_ads,
      n_ads_as_of_day: group.ads.filter((a) => a.day < pos).length,
      n_phones: group.n_phones,
    },
    detection: {
      first_ad_day: dayNo(group.first_day),
      first_ad_date: isoOf(data.start, group.first_day),
      flagged_day: group.flag_day === null ? null : dayNo(group.flag_day),
      flagged_date: group.flag_day === null ? null : isoOf(data.start, group.flag_day),
      days_to_detect: group.gap_days,
      ads_up_before_flag: group.ads_before_flag,
      ad_days_before_flag: group.ad_days_before_flag,
      renters_estimate: group.renters_est,
      renters_estimate_basis: `ESTIMATE, not measured: ad-days before the flag times ${data.views_per_ad_day} renters per ad per day (an assumption)`,
    },
    method:
      `The ring finder is run once per day on the ads posted so far. Ads that ask for money ` +
      `first are joined by the signals below, each with its weight; a group is reported at ` +
      `${data.min_ads} or more ads under 2 or more numbers. Weight 0 means shown for context, ` +
      `not used to join ads.`,
    signals: rows.map((r) => ({
      kind: r.kind,
      name: KIND_NAME[r.kind],
      weight: r.weight,
      shared_values: r.values,
      ads_linked: r.ads,
      values: group.signals
        .filter((s) => s.kind === r.kind)
        .map((s) => ({ key: s.key, label: s.label, ad_ids: s.ad_ids })),
    })),
    findings: group.findings,
    answer_key_check: group.answer_key,
    ads: group.ads.map((a) => ({
      id: a.id,
      day: dayNo(a.day),
      date: isoOf(data.start, a.day),
      phone: a.phone,
      area: a.hood,
      rent: a.rent,
    })),
  };
}

/** The same case file as a page of plain text, for printing. */
export function caseFileText(file: CaseFile): string {
  const d = file.detection;
  const lines = [
    `${file.label} · ${file.source}`,
    file.notice,
    "",
    `CASE FILE: ${file.group.label}`,
    `${file.group.n_ads} ads under ${file.group.n_phones} numbers, in a stream of ${file.stream.n_ads} ads over ${file.stream.days} days (seed ${file.stream.seed}).`,
    "",
    "WHEN",
    `First ad: day ${d.first_ad_day} (${d.first_ad_date})`,
    d.flagged_day === null
      ? "Flagged: not flagged"
      : `Flagged: day ${d.flagged_day} (${d.flagged_date}), ${d.days_to_detect} days after the first ad`,
    `Up before the flag: ${d.ads_up_before_flag} ads for ${d.ad_days_before_flag} ad-days`,
    `Renters who may have seen them: about ${d.renters_estimate.toLocaleString("en-US")}. ${d.renters_estimate_basis}.`,
    "",
    "WHY THESE ADS ARE LINKED",
    ...file.signals.map(
      (s) =>
        `- ${s.name}: ${s.shared_values} shared, linking ${s.ads_linked} ads (weight ${s.weight})`,
    ),
    "",
    "HOW",
    file.method,
    "",
    "FINDINGS",
    ...file.findings.map((f) => `- ${f.title}: ${f.summary} (link strength ${f.score.toFixed(2)})`),
    "",
    "CHECK AGAINST THE ANSWER KEY (seeded ring: ads in this group)",
    Object.entries(file.answer_key_check)
      .map(([name, n]) => `${name}: ${n}`)
      .join(", "),
    "",
    `ADS (${file.ads.length})`,
    ...file.ads.map(
      (a) => `ad ${a.id} · day ${a.day} (${a.date}) · ${a.phone} · ${a.area} · $${a.rent}/month`,
    ),
  ];
  return lines.join("\n");
}

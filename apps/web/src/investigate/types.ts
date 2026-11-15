// The /forensics API's shapes (src/snapback/api/forensics.py). All of it is SYNTHETIC data.

export interface Evidence {
  ad_id: number;
  span: string | null;
  note: string | null;
  photo_ids: string[];
  phone: string | null;
  rule_id: string | null;
  score: number | null;
}

export interface Finding {
  id: string;
  kind: string;
  title: string;
  summary: string;
  score: number;
  evidence: Evidence[];
}

export interface TimelineEvent {
  date: string;
  ad_id: number;
  kind: string;
  detail: string;
}

export interface RingFull {
  id: string;
  label: string;
  ad_ids: number[];
  phones: string[];
  photo_sets: string[];
  first_seen: string;
  last_seen: string;
  score: number;
  sources: number[];
  findings: Finding[];
  timeline: TimelineEvent[];
  weekly: [string, number][];
}

export interface RingSummary {
  id: string;
  label: string;
  n_ads: number;
  n_phones: number;
  first_seen: string;
  last_seen: string;
  score: number;
  finding_kinds: string[];
}

export interface Score {
  ad_precision: number;
  ad_recall: number;
  honest_flagged: number;
  n_honest: number;
  ring_precision: number;
  ring_recall: number;
  rings_found: number;
  rings_recovered: number;
}

export interface RingsResponse {
  label: string;
  synthetic: boolean;
  source: string;
  n_ads: number;
  rings: RingSummary[];
  metrics: { n_ads: number; n_true_rings: number; pipeline: Score; keyword_baseline: Score };
  example_questions: string[];
}

export interface GraphNode {
  id: string;
  type: "ad" | "phone" | "photo" | "phrase";
  label: string;
  date?: string;
}

export interface AdCard {
  id: number;
  posted_at: string;
  phone: string;
  hood: string;
  rent: number;
  text: string;
  photos: string[];
}

export interface RingResponse {
  label: string;
  synthetic: boolean;
  source: string;
  ring: RingFull;
  graph: { nodes: GraphNode[]; edges: { source: string; target: string }[] };
  ads: AdCard[];
}

export interface Answer {
  question: string;
  answer: string;
  grounded: boolean;
  intent: string;
  evidence: Evidence[];
  mode: string;
  synthetic: boolean;
}

// The case file (GET /forensics/rings/{id}/case-file) and the case study (GET /forensics/case-study).
export type TieKind = "phone" | "photo" | "wording" | "link";

export interface AmountAsked {
  sentence: string | null;
  item: string | null;
  usd: number | null;
  basis: string;
}

export interface CaseAd {
  id: number;
  posted_at: string;
  phone: string;
  hood: string;
  beds: number;
  rent: number;
  title: string;
  text: string;
  photos: string[];
  amount_asked: AmountAsked;
}

export interface CaseLink {
  from_ad: number;
  to_ad: number;
  kind: TieKind;
  weight: number;
  evidence: {
    phone?: string;
    photo_sets?: number;
    ids_older?: string[];
    ids_newer?: string[];
    closest_bits?: number;
    strong?: boolean;
    span_older?: string;
    span_newer?: string;
    reworded?: boolean;
    hosts?: string[];
  };
}

export interface CaseSignal {
  kind: TieKind;
  label: string;
  weight: number;
  n_links: number;
  strength: number;
  ads: number[];
}

export interface CaseFile {
  schema: string;
  label: string;
  synthetic: boolean;
  source: string;
  ring: {
    id: string;
    label: string;
    n_ads: number;
    n_phones: number;
    first_seen: string;
    last_seen: string;
    score: number;
  };
  detection: {
    first_ad_id: number;
    first_ad_date: string;
    flagged_on: string | null;
    flag_ad_id: number | null;
    days_first_ad_to_flag: number | null;
    ads_up_before_flag: number;
    ads_total: number;
    method: string;
  };
  timeline: CaseAd[];
  contacts: { phone: string; ad_ids: number[] }[];
  links: CaseLink[];
  signals: CaseSignal[];
  strongest: TieKind[];
  findings: { kind: string; title: string; summary: string; score: number }[];
  sources: number[];
  not_known: string[];
}

export interface StudyStep {
  step: number;
  date: string;
  day_no: number;
  ad_ids: number[];
  ring_ads_so_far: number;
  numbers_so_far: number;
  ties: (CaseLink & { from_ad: number; to_ad: number })[];
  lines: string[];
  detector: string;
  flagged: boolean;
}

export interface CaseStudy {
  schema: string;
  label: string;
  synthetic: boolean;
  source: string;
  ring: { id: string; label: string; n_ads: number };
  flagged_on: string | null;
  days_first_ad_to_flag: number | null;
  steps: StudyStep[];
  after: { n_ads: number; last_date: string | null; text: string };
  strongest: TieKind[];
  not_known: string[];
}

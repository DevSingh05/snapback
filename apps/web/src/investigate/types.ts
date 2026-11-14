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

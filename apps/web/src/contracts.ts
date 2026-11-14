// Mirrors the Card shapes in src/snapback/contracts.py. Keep the two in step; the XO owns both.

export type DataSource = "live" | "fixture";
export type VerdictState = "verified" | "hold" | "dont_pay" | "unverified";
export type CardRowKind = "place" | "person" | "price";
export type CardTone = "ok" | "hold" | "red_flag" | "not_shown" | "not_checked";

export interface CardLine {
  label: string;
  text: string;
  tone: CardTone;
}

export interface CardRow {
  kind: CardRowKind;
  lines: CardLine[];
}

export interface Card {
  case_id: string;
  source: DataSource;
  state: VerdictState;
  checked_at: string;
  expires_at: string;
  rows: CardRow[];
  not_checked: string[];
  footer: string[];
  verify_url?: string | null;
  lang: string;
}

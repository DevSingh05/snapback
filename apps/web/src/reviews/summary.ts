// The maths behind /reviews. Pure functions so the page and the tests share one source.
export interface ReviewResponse {
  q1_easy: number;
  q2_would_pay: "yes" | "no" | "not sure";
  q3_trust: number;
  q4_use_again: "yes" | "maybe" | "no";
  q6_quote?: string;
  q6_name?: string;
  q7_rented?: boolean;
}

export interface ReviewsFile {
  updated: string;
  form_url: string;
  responses: ReviewResponse[];
}

export interface ReviewsSummary {
  n: number;
  avgEasy: number | null;
  avgTrust: number | null;
  useAgainPct: number | null;
  wouldNotPayPct: number | null;
}

export interface PublicQuote {
  quote: string;
  by: string;
}

const mean = (xs: number[]): number | null =>
  xs.length === 0 ? null : Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10;

const pct = (hits: number, n: number): number | null =>
  n === 0 ? null : Math.round((hits / n) * 100);

export function summarize(responses: ReviewResponse[]): ReviewsSummary {
  const n = responses.length;
  return {
    n,
    avgEasy: mean(responses.map((r) => r.q1_easy)),
    avgTrust: mean(responses.map((r) => r.q3_trust)),
    useAgainPct: pct(responses.filter((r) => r.q4_use_again === "yes").length, n),
    wouldNotPayPct: pct(responses.filter((r) => r.q2_would_pay === "no").length, n),
  };
}

// First name or initials only: whatever is typed after the first word is dropped.
export function firstNameOnly(name: string | undefined): string {
  const first = (name ?? "").trim().split(/\s+/)[0] ?? "";
  return first.slice(0, 24) || "Anonymous";
}

// Only rows where the reviewer wrote a quote for us to share.
export function publicQuotes(responses: ReviewResponse[]): PublicQuote[] {
  const out: PublicQuote[] = [];
  for (const r of responses) {
    const quote = (r.q6_quote ?? "").trim();
    if (quote) out.push({ quote, by: firstNameOnly(r.q6_name) });
  }
  return out;
}

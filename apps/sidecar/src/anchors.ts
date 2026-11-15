/**
 * The anchor of one card line ("label: text") on the web case card, so an iMessage red flag can
 * link to its proof: /case/<id>#check-<label slug>. The web card applies the same rule
 * (apps/web/src/case/checkAnchor.ts), and both test files share the same vectors.
 */
export function checkAnchor(line: string): string | null {
  const cut = line.indexOf(": ");
  if (cut < 1) return null;
  const slug = line
    .slice(0, cut)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug ? `check-${slug}` : null;
}

/** The web card's "What checks out, and what doesn't" section (Checks.tsx `id="checks"`). */
export const CHECKS_SECTION = "checks";

/** Red-flag links per reply, at most (XO 03:32: keep replies short). */
export const MAX_FLAG_LINKS = 3;

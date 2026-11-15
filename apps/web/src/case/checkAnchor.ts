/**
 * The anchor of one card line ("label: text"): `check-<label slug>`. The iMessage reply links
 * each red flag to /case/<id>#<this> (apps/sidecar/src/anchors.ts applies the same rule, and both
 * test files share the same vectors).
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

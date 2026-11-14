import type { DataSource } from "../contracts";

// Hard rule 5: every screen shows whether its data is LIVE or FIXTURE.
export function SourceChip({ source }: { source: DataSource }) {
  const label = source === "live" ? "LIVE" : "FIXTURE";
  const hint =
    source === "live" ? "Real data from a real check" : "Synthetic sample data made by the team";
  return (
    <span className={`chip chip-${source}`} data-testid="source-chip" title={hint}>
      <span className="chip-dot" aria-hidden="true" />
      {label}
      <span className="sr-only">. {hint}</span>
    </span>
  );
}

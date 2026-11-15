// The record line (design v4 1.5): under any value that comes from a record, one mono line
// names the source, then the date only when the API gave one, then LIVE or FIXTURE.
// The date is shown as given; this helper never invents or reformats one.
import type { DataSource } from "../contracts";
import "./ui.css";

export type RecordSource = "costar" | "scan" | "county" | "license" | "aerial";

export const RECORD_SOURCE: Record<RecordSource, string> = {
  costar: "COSTAR RECORD",
  scan: "3D SCAN",
  county: "COUNTY RECORD",
  license: "TEXAS LICENSE LIST",
  aerial: "AERIAL · VEXCEL",
};

interface RecordLineProps {
  source: RecordSource;
  // As the API gave it. Leave out when the API gave none.
  date?: string | null;
  // true or "live" prints LIVE; false or "fixture" prints FIXTURE; leave out to print neither.
  live?: boolean | DataSource;
  className?: string;
}

export function recordLineText({ source, date, live }: Omit<RecordLineProps, "className">): string {
  const parts = [RECORD_SOURCE[source]];
  if (date && date.trim()) parts.push(`AS OF ${date.trim()}`);
  if (live !== undefined) parts.push(live === true || live === "live" ? "LIVE" : "FIXTURE");
  return parts.join(" · ");
}

export function RecordLine({ className, ...rest }: RecordLineProps) {
  const isLive = rest.live === true || rest.live === "live";
  return (
    <span
      className={`ui-record${isLive ? " ui-record-live" : ""}${className ? ` ${className}` : ""}`}
      data-testid="record-line"
    >
      {recordLineText(rest)}
    </span>
  );
}

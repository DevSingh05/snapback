// LIVE or FIXTURE (hard rule 5), as a mono word with a 7px square before it: green for LIVE,
// grey for FIXTURE. No tile, no ground. One per screen at page level, plus stamps on photos.
import type { DataSource } from "../contracts";
import "./ui.css";

export const TAG_HINT: Record<DataSource, string> = {
  live: "Real data from a real check",
  fixture: "Synthetic sample data made by the team",
};

interface TagProps {
  source: DataSource;
  className?: string;
  testId?: string;
}

export function Tag({ source, className, testId }: TagProps) {
  return (
    <span
      className={`ui-tag ui-tag-${source}${className ? ` ${className}` : ""}`}
      data-testid={testId}
      title={TAG_HINT[source]}
    >
      {source === "live" ? "LIVE" : "FIXTURE"}
      <span className="sr-only">. {TAG_HINT[source]}</span>
    </span>
  );
}

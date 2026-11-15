import type { DataSource } from "../contracts";
import { Tag } from "../ui/Tag";

// Hard rule 5: every screen shows whether its data is LIVE or FIXTURE. Drawn by ui/Tag.
export function SourceChip({ source }: { source: DataSource }) {
  return <Tag source={source} className={`chip chip-${source}`} testId="source-chip" />;
}

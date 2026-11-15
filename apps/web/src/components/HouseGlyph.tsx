// The house is now the SNAPBACK mark (ui/Mark.tsx): the offset house, two flat shapes that
// survive 16px. This file keeps the old names so every screen that imports HouseGlyph or
// Wordmark keeps working. It is decoration: aria-hidden, and it never carries a word.
import { Lockup, Mark } from "../ui/Mark";

export { Mark } from "../ui/Mark";

interface Props {
  className?: string;
  // The record half in the accent. Off (grey) for empty and error states.
  lit?: boolean;
  // Kept for old callers; the mark has one level of detail.
  detail?: "full" | "low";
}

export function HouseGlyph({ className, lit = true }: Props) {
  return (
    <Mark
      lit={lit}
      className={`house${lit ? " house-lit" : ""}${className ? ` ${className}` : ""}`}
    />
  );
}

export function Wordmark() {
  return <Lockup className="wordmark" />;
}

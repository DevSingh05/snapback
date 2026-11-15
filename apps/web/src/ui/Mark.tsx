// The SNAPBACK mark. Variant "a" (the default) is the offset house: one house in two halves
// that do not line up, the ad on the left in ink and the record on the right in the accent.
// On hover of the nearest link or .ui-lockup the halves slide level (off under reduced motion).
// Variants "b" (the return roof) and "c" (the checked pin) are kept so the pick can be swapped
// in one place: change DEFAULT_MARK. Decoration only: aria-hidden, never carries a word.
import "./ui.css";

export type MarkVariant = "a" | "b" | "c";

export const DEFAULT_MARK: MarkVariant = "a";

// Path data on a 24 unit grid. `l` is drawn in currentColor, `r` in --mark-act, `cut` in the
// ground colour (--mark-cut).
export const MARK_PATHS: Record<MarkVariant, Array<{ part: "l" | "r" | "cut"; d: string }>> = {
  a: [
    { part: "l", d: "M2 11.6 11.25 4.2V22.5H2z" },
    { part: "r", d: "M12.75 1.5 22 8.9v11.1h-9.25z" },
  ],
  b: [
    { part: "l", d: "M4.5 21.5V11L12 4l7.5 7M4.5 21.5h15" },
    { part: "r", d: "M19.5 5.2V11h-5.8" },
  ],
  c: [
    { part: "l", d: "M3.5 1.5h17v15L12 23l-8.5-6.5z" },
    { part: "cut", d: "M7.8 9.6l3 3 5.6-6" },
  ],
};

interface MarkProps {
  variant?: MarkVariant;
  // Width and height in px. Leave unset to size it from CSS.
  size?: number;
  // The record half in the accent. Off (grey) for empty and error states.
  lit?: boolean;
  className?: string;
}

export function Mark({ variant = DEFAULT_MARK, size, lit = true, className }: MarkProps) {
  return (
    <svg
      className={`ui-mark ui-mark-${variant}${lit ? "" : " ui-mark-off"}${className ? ` ${className}` : ""}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      {MARK_PATHS[variant].map((p) => (
        <path key={p.part} className={`ui-mark-${p.part}`} d={p.d} />
      ))}
    </svg>
  );
}

interface LockupProps {
  variant?: MarkVariant;
  // On a matte band or a photograph: the record half takes the matte accent.
  onMatte?: boolean;
  className?: string;
}

// The mark, a 10px gap, then the name.
export function Lockup({ variant, onMatte = false, className }: LockupProps) {
  return (
    <span
      className={`ui-lockup${onMatte ? " ui-on-matte" : ""}${className ? ` ${className}` : ""}`}
    >
      <Mark variant={variant} size={22} />
      SNAPBACK
    </span>
  );
}

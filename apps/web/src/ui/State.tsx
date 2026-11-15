// A row's state: a 10px square in the state colour, then the word in ink. The word is always
// there, so colour never stands alone. Pass children to show a different word (for example a
// short verdict from cardStrings.ts); never type a verdict sentence here.
import type { ReactNode } from "react";

import "./ui.css";

export type StateKind = "ok" | "mismatch" | "warn" | "unconfirmed" | "unchecked";

export const STATE_LABEL: Record<StateKind, string> = {
  ok: "Matches",
  mismatch: "Doesn't match",
  warn: "Warning",
  unconfirmed: "Not confirmed",
  unchecked: "Not checked",
};

interface StateProps {
  kind: StateKind;
  children?: ReactNode;
  className?: string;
}

export function State({ kind, children, className }: StateProps) {
  return (
    <span
      className={`ui-state ui-state-${kind}${className ? ` ${className}` : ""}`}
      data-state={kind}
    >
      {children ?? STATE_LABEL[kind]}
    </span>
  );
}

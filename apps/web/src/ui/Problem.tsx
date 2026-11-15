// Problem (design v4 section 4): a row with the grey "Not checked" square, what happened in
// plain words, and one action. A failed check is never shown as a pass or as a warning.
import { Action } from "./Action";
import { State } from "./State";
import type { StateAction } from "./states";
import "./ui.css";

interface ProblemProps {
  // What happened and what to do, in plain words.
  message: string;
  action?: StateAction;
  className?: string;
}

export function Problem({ message, action, className }: ProblemProps) {
  return (
    <div
      className={`ui-problem${className ? ` ${className}` : ""}`}
      role="alert"
      data-testid="problem"
    >
      <State kind="unchecked" />
      <p>{message}</p>
      {action && <Action action={action} />}
    </div>
  );
}

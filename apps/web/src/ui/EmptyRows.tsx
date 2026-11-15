// Empty (design v4 section 4): never a picture or a hero block. One plain sentence, up to two
// example rows in muted type under the real heading, and the one action. With onExample the
// examples are buttons that send themselves (Finder starters); without it they are text.
import { Action } from "./Action";
import type { StateAction } from "./states";
import "./ui.css";

interface EmptyRowsProps {
  message: string;
  examples?: string[];
  onExample?: (text: string) => void;
  action?: StateAction;
  className?: string;
}

export function EmptyRows({
  message,
  examples = [],
  onExample,
  action,
  className,
}: EmptyRowsProps) {
  return (
    <div className={`ui-empty${className ? ` ${className}` : ""}`} data-testid="empty-rows">
      <p className="ui-empty-msg">{message}</p>
      {examples.length > 0 && (
        <ul className="ui-empty-rows">
          {examples.slice(0, 2).map((text) => (
            <li key={text}>
              {onExample ? (
                <button type="button" onClick={() => onExample(text)}>
                  {text}
                </button>
              ) : (
                <span>{text}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {action && <Action action={action} />}
    </div>
  );
}

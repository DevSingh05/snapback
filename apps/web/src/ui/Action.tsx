import type { StateAction } from "./states";

// The one action under an empty or problem row: quiet, 48px, a link when it has an address.
export function Action({ action }: { action: StateAction }) {
  return action.href ? (
    <a className="ui-btn-quiet" href={action.href} onClick={action.onClick}>
      {action.label}
    </a>
  ) : (
    <button type="button" className="ui-btn-quiet" onClick={action.onClick}>
      {action.label}
    </button>
  );
}

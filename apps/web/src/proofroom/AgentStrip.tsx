// The check team as one compact row: a square per member that lights as it works and takes
// its finding's colour when done, always with its name and state in words. Used on the report
// and on Home while a check runs; the Proof Room shows the same desks in full.
import "./proofroom.css";
import type { Desk, Lang } from "./model";
import { WORDS } from "./words";

/** The state word for a desk, with what it found when it is done. */
export function deskWord(desk: Desk, lang: Lang): string {
  const w = WORDS[lang];
  if (desk.state !== "done") return w.state[desk.state];
  const tone = { red_flag: "Red flag", hold: "Hold", not_shown: "Not shown", ok: "Checks out" }[
    desk.tone as string
  ];
  return tone && lang === "en" ? tone : w.state.done;
}

// The strip keeps every state to one line, so a light changing never moves the row under it.
const SHORT_UNUSED: Record<Lang, string> = { en: "Not used", es: "No se usó" };

export function AgentStrip({
  desks,
  lang = "en",
  label,
  hrefFor,
  onPick,
}: {
  desks: Desk[];
  lang?: Lang;
  label: string;
  // When given, each member links to its desk in the Proof Room.
  hrefFor?: (deskId: string) => string;
  // When given, each member is a button that opens its card.
  onPick?: (deskId: string) => void;
}) {
  return (
    <ol className="pr-strip" aria-label={label} data-testid="agent-strip">
      {desks.map((desk) => {
        const body = (
          <>
            <span className="pr-strip-light" aria-hidden="true" />
            <span className="pr-strip-name">{desk.card.name}</span>
            <span className="pr-strip-state ui-mono">
              {desk.state === "unused" ? (
                <>
                  <span aria-hidden="true">{SHORT_UNUSED[lang]}</span>
                  <span className="sr-only">{deskWord(desk, lang)}</span>
                </>
              ) : (
                deskWord(desk, lang)
              )}
            </span>
          </>
        );
        return (
          <li
            key={desk.card.id}
            className="pr-strip-item"
            data-state={desk.state}
            data-tone={desk.tone}
            data-testid="agent-strip-item"
            data-agent={desk.card.id}
          >
            {onPick ? (
              <button type="button" onClick={() => onPick(desk.card.id)}>
                {body}
              </button>
            ) : hrefFor ? (
              <a href={hrefFor(desk.card.id)}>{body}</a>
            ) : (
              <span className="pr-strip-in">{body}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

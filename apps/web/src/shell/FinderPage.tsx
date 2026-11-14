import { useState } from "react";

import { loadFinderEvents, recordFinderEvent, type FinderEvent } from "./finderStore";
import "./shell.css";

const KIND_LABEL: Record<FinderEvent["kind"], string> = {
  opened: "You opened",
  passed: "You passed on",
  criteria: "You changed a filter",
  remembered: "Remembered",
  note: "Your note",
};

const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

// The Finder as its own view: what you did on the map this visit, what it was asked to
// remember, and a box for notes. It is honest about what answers: today offers are picked by
// code and stamped "Picked by policy"; the finder agent's replies are not built yet, so nothing
// replies to a note.
export function FinderPage() {
  const [events, setEvents] = useState<FinderEvent[]>(() => loadFinderEvents());
  const [text, setText] = useState("");
  const remembered = events.filter((e) => e.kind === "remembered");

  return (
    <div className="view" data-testid="finder-page">
      <header className="view-head">
        <p className="view-eyebrow mono">Finder</p>
        <h1 className="view-title">What the finder has learned</h1>
        <p className="view-lead">
          It watches what you open and pass on, and asks before it remembers anything.
        </p>
      </header>
      <div className="view-body view-split">
        <section className="fd-panel" aria-label="What you did">
          <h2 className="fd-h">This visit</h2>
          {events.length === 0 ? (
            <p className="fd-empty" data-testid="finder-empty">
              Nothing yet. Open a place on the map or pass on one, and it shows here.{" "}
              <a href="/map">Open the map</a>
            </p>
          ) : (
            <ol className="fd-log" aria-live="polite">
              {events.map((e, i) => (
                <li key={`${e.at}-${i}`} className="fd-ev" data-kind={e.kind}>
                  <span className="fd-kind mono">{KIND_LABEL[e.kind] ?? e.kind}</span>
                  <span className="fd-text">{e.text}</span>
                  <span className="fd-time mono">{time(e.at)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
        <div className="fd-side">
          <section className="fd-panel" aria-label="What it remembers">
            <h2 className="fd-h">Remembered</h2>
            {remembered.length === 0 ? (
              <p className="fd-empty">
                Nothing remembered. Offers such as &quot;Remember: no walk-ups?&quot; appear on the
                map after you pass on a few places, stamped{" "}
                <span className="fd-stamp mono">Picked by policy</span>.
              </p>
            ) : (
              <ul className="fd-kept">
                {remembered.map((e, i) => (
                  <li key={`${e.at}-${i}`}>{e.text}</li>
                ))}
              </ul>
            )}
          </section>
          <form
            className="fd-panel fd-form"
            aria-label="Leave a note"
            onSubmit={(e) => {
              e.preventDefault();
              const note = text.trim();
              if (!note) return;
              setEvents(recordFinderEvent("note", note));
              setText("");
            }}
          >
            <label className="fd-h" htmlFor="finder-note">
              Tell the finder what matters
            </label>
            <textarea
              id="finder-note"
              className="fd-input"
              rows={3}
              value={text}
              placeholder="For example: ground floor only, near a bus line"
              onChange={(e) => setText(e.target.value)}
            />
            <p className="fd-honest" data-testid="finder-honest">
              Your note is saved to this visit&apos;s list. Nothing replies yet: the finder
              agent&apos;s answers are not built. Today&apos;s offers are picked by code and stamped{" "}
              <span className="fd-stamp mono">Picked by policy</span>.
            </p>
            <button type="submit" className="fd-send" disabled={!text.trim()}>
              Save note
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

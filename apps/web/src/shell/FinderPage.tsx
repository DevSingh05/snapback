import { useState } from "react";

import { PlacesStrip } from "../search/PlacesStrip";
import { loadFinderEvents, recordFinderEvent, type FinderEvent } from "./finderStore";
import {
  briefFromChips,
  chipFromWords,
  loadLearned,
  nextOffer,
  OFFER_STAMP,
  saveLearned,
  type Chip,
} from "./finderRules";
import "./shell.css";

const KIND_LABEL: Record<FinderEvent["kind"], string> = {
  opened: "You opened",
  passed: "You passed on",
  criteria: "You changed a filter",
  remembered: "Remembered",
  note: "You",
};

// The Finder: a conversation, what it has learned about you, and the places that fit. The
// deep agent that will answer here is not wired yet, and the page says so: today the only
// thing on the Finder's side of the conversation is an offer picked by code, stamped
// "Picked by our rules". No reply is ever made up.
export function FinderPage() {
  const [events, setEvents] = useState<FinderEvent[]>(() => loadFinderEvents());
  const [learned, setLearned] = useState(() => loadLearned());
  const [text, setText] = useState("");
  const [own, setOwn] = useState("");
  const offer = nextOffer(events, learned.chips, learned.declined);
  const thread = [...events].reverse(); // oldest first, like a conversation

  const keep = (next: { chips: Chip[]; declined: string[] }) => {
    setLearned(next);
    saveLearned(next);
  };
  const addChip = (chip: Chip) =>
    keep({ ...learned, chips: [...learned.chips.filter((c) => c.id !== chip.id), chip] });

  return (
    <div className="view" data-testid="finder-page">
      <header className="view-head">
        <p className="view-eyebrow mono">Finder</p>
        <h1 className="view-title">Tell it what you want in a home</h1>
      </header>
      <div className="view-body fd-grid">
        <section className="fd-panel fd-talk" aria-label="Conversation">
          <h2 className="fd-h">Conversation</h2>
          <p className="fd-honest" data-testid="finder-honest">
            The finder agent&apos;s replies are not built yet, so nothing answers your messages.
            Until it is, offers here are picked by code and stamped{" "}
            <span className="fd-stamp mono">{OFFER_STAMP}</span>.
          </p>
          {thread.length === 0 ? (
            <p className="fd-empty" data-testid="finder-empty">
              Nothing yet. Say what matters to you below, or open and pass on places on the map.
            </p>
          ) : (
            <ol className="fd-thread" aria-live="polite">
              {thread.map((e, i) => (
                <li
                  key={`${e.at}-${i}`}
                  className="fd-msg"
                  data-kind={e.kind}
                  data-testid="finder-msg"
                >
                  <span className="fd-kind mono">{KIND_LABEL[e.kind] ?? e.kind}</span>
                  <span className="fd-text">{e.text}</span>
                </li>
              ))}
            </ol>
          )}
          {offer && (
            <div className="fd-offer" data-testid="finder-offer">
              <span className="fd-stamp mono">{OFFER_STAMP}</span>
              <p className="fd-offer-text">Remember: {offer.label}?</p>
              <div className="fd-offer-acts">
                <button type="button" onClick={() => addChip(offer)}>
                  Yes, remember
                </button>
                <button
                  type="button"
                  className="fd-quiet"
                  onClick={() => keep({ ...learned, declined: [...learned.declined, offer.id] })}
                >
                  No
                </button>
              </div>
            </div>
          )}
          <form
            className="fd-form"
            aria-label="Send a message"
            onSubmit={(e) => {
              e.preventDefault();
              const note = text.trim();
              if (!note) return;
              setEvents(recordFinderEvent("note", note));
              setText("");
            }}
          >
            <label className="sr-only" htmlFor="finder-note">
              Your message
            </label>
            <textarea
              id="finder-note"
              className="fd-input"
              rows={2}
              value={text}
              placeholder="For example: no walk-ups, under $1,500, near downtown"
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit" className="fd-send" disabled={!text.trim()}>
              Send
            </button>
          </form>
        </section>
        <section className="fd-panel fd-learned" aria-label="What I've learned about you">
          <h2 className="fd-h">What I&apos;ve learned about you</h2>
          {learned.chips.length === 0 ? (
            <p className="fd-empty" data-testid="learned-empty">
              Nothing yet. It only keeps what you say yes to, and you can remove anything.
            </p>
          ) : (
            <ul className="fd-chips">
              {learned.chips.map((c) => (
                <li key={c.id} className="fd-chip" data-testid="learned-chip">
                  {c.label}
                  <button
                    type="button"
                    className="fd-chip-x"
                    aria-label={`Forget ${c.label}`}
                    onClick={() =>
                      keep({ ...learned, chips: learned.chips.filter((x) => x.id !== c.id) })
                    }
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form
            className="fd-add"
            aria-label="Add a preference"
            onSubmit={(e) => {
              e.preventDefault();
              const label = own.trim();
              if (!label) return;
              addChip(chipFromWords(label) ?? { id: `note:${label.toLowerCase()}`, label });
              setOwn("");
            }}
          >
            <label className="sr-only" htmlFor="finder-own">
              Add something yourself
            </label>
            <input
              id="finder-own"
              className="fd-own"
              value={own}
              placeholder="Add one yourself, e.g. near downtown"
              onChange={(e) => setOwn(e.target.value)}
            />
            <button type="submit" className="fd-quiet" disabled={!own.trim()}>
              Add
            </button>
          </form>
          <p className="fd-honest">
            Rent, bedrooms, walk-ups, parking and pets narrow the places below. Anything else is
            kept as your note and does not filter yet.
          </p>
        </section>
        <section className="fd-results" aria-label="Places that fit">
          <PlacesStrip
            caseId={null}
            brief={briefFromChips(learned.chips)}
            heading="Places that fit what I know"
          />
        </section>
      </div>
    </div>
  );
}

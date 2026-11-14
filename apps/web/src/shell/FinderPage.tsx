import { useCallback, useEffect, useRef, useState } from "react";

import { apiBase } from "../api";
import { SourceChip } from "../components/SourceChip";
import type {
  FinderPick,
  FinderProposal,
  FinderSignal,
  FinderState,
  FinderTraceEvent,
} from "../contracts";
import { PlacesStrip } from "../search/PlacesStrip";
import {
  decide,
  FinderBusy,
  FinderGone,
  FinderOffline,
  getState,
  keptLabel,
  learnedLines,
  loadAuth,
  saveAuth,
  sendMessage,
  STAMP,
  startSession,
  type FinderAuth,
} from "./finderApi";
import {
  loadFinderEvents,
  loadThread,
  markSignalsSent,
  recordFinderEvent,
  saveThread,
  unsentSignals,
  type FinderEvent,
  type FinderTurn,
} from "./finderStore";
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

/** After this long the working line says a full run can take about half a minute. */
const SLOW_MS = 6000;

type Conn =
  | { state: "connecting" }
  | { state: "offline"; why: "none" | "down" }
  | { state: "ready"; auth: FinderAuth; fs: FinderState };

// The Finder: the deep agent that learns what the renter wants and helps them find it. When the
// Finder service runs, every message and every pick or pass on the map goes to it; it replies,
// offers what to remember (nothing applies until Yes) and leads the list. Without the service the
// page says so and falls back to code rules on this device. No reply is ever made up.
export function FinderPage() {
  const [conn, setConn] = useState<Conn>(() =>
    apiBase() ? { state: "connecting" } : { state: "offline", why: "none" },
  );

  useEffect(() => {
    if (conn.state !== "connecting") return;
    let live = true;
    (async () => {
      try {
        const saved = loadAuth();
        if (saved) {
          try {
            const fs = await getState(saved);
            if (live) setConn({ state: "ready", auth: saved, fs });
            return;
          } catch (err) {
            if (!(err instanceof FinderGone)) throw err;
            saveAuth(null);
            saveThread([]);
          }
        }
        const fresh = await startSession();
        const auth = { sid: fresh.sid, token: fresh.token };
        const fs = await getState(auth);
        if (live) setConn({ state: "ready", auth, fs });
      } catch {
        if (live) setConn({ state: "offline", why: "down" });
      }
    })();
    return () => {
      live = false;
    };
  }, [conn.state]);

  return (
    <div className="view" data-testid="finder-page">
      <header className="view-head">
        <p className="view-eyebrow mono">Finder</p>
        <h1 className="view-title">Tell it what you want in a home</h1>
      </header>
      {conn.state === "ready" ? (
        <LiveFinder
          auth={conn.auth}
          initial={conn.fs}
          onOffline={() => setConn({ state: "offline", why: "down" })}
          onRestart={() => {
            saveAuth(null);
            saveThread([]);
            setConn({ state: "connecting" });
          }}
        />
      ) : conn.state === "connecting" ? (
        <p className="fd-connecting view-body" data-testid="finder-connecting">
          Connecting to the Finder…
        </p>
      ) : (
        <OfflineFinder why={conn.why} onRetry={() => setConn({ state: "connecting" })} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Live: the Finder service answers.

type Item =
  { at: string; type: "turn"; turn: FinderTurn } | { at: string; type: "did"; event: FinderEvent };

function signalWords(s: FinderSignal): string {
  const what = s.place_kind ?? "place";
  const bits = [
    s.walkup === true ? "a walk-up" : s.walkup === false ? "no walk-up" : null,
    s.parking === false ? "no parking" : s.parking === true ? "parking" : null,
    s.has_scan ? "a 3D scan" : null,
  ].filter(Boolean);
  const verb = s.kind === "pass" ? "You passed on" : "You liked";
  return `${verb} an ${what === "apartment" ? "apartment" : what === "house" ? "house" : "place"}${
    bits.length ? ` (${bits.join(", ")})` : ""
  }`.replace("an house", "a house");
}

function LiveFinder({
  auth,
  initial,
  onOffline,
  onRestart,
}: {
  auth: FinderAuth;
  initial: FinderState;
  onOffline: () => void;
  onRestart: () => void;
}) {
  const [fs, setFs] = useState<FinderState>(initial);
  const [thread, setThread] = useState<FinderTurn[]>(() => loadThread());
  const [events, setEvents] = useState<FinderEvent[]>(() => loadFinderEvents());
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<null | { since: number; what: string }>(null);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answering, setAnswering] = useState<string | null>(null);
  const sentOnce = useRef(false);

  const push = useCallback((turn: FinderTurn) => {
    setThread((prev) => {
      const next = [...prev, turn];
      saveThread(next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!busy) return;
    setSlow(false);
    const t = window.setTimeout(() => setSlow(true), SLOW_MS);
    return () => window.clearTimeout(t);
  }, [busy]);

  const refresh = useCallback(async () => {
    try {
      setFs(await getState(auth));
    } catch {
      // The reply already showed; the panels catch up on the next turn.
    }
  }, [auth]);

  const run = useCallback(
    async (words: string | null, extra: FinderSignal[], what: string) => {
      setError(null);
      const fromMap = unsentSignals(loadFinderEvents());
      const signals = [...fromMap, ...extra];
      if (!words && signals.length === 0) return;
      if (words) push({ at: new Date().toISOString(), who: "you", text: words });
      setBusy({ since: Date.now(), what });
      try {
        const reply = await sendMessage(auth, words, signals);
        if (fromMap.length) setEvents(markSignalsSent());
        push({
          at: new Date().toISOString(),
          who: "finder",
          text: reply.reply,
          by: reply.reply_by,
        });
        await refresh();
      } catch (err) {
        if (err instanceof FinderOffline) {
          if (words) recordFinderEvent("note", words);
          onOffline();
          return;
        }
        if (err instanceof FinderBusy) {
          setError("Still thinking about your last message. Give it a moment, then send again.");
        } else if (err instanceof FinderGone) {
          setError("This Finder session ended on the server. Start over to begin a new one.");
        } else {
          setError(err instanceof Error ? err.message : "The Finder could not answer.");
        }
      } finally {
        setBusy(null);
      }
    },
    [auth, onOffline, push, refresh],
  );

  // What you did on the map since the last turn goes to the Finder as soon as you open this tab.
  useEffect(() => {
    if (sentOnce.current) return;
    sentOnce.current = true;
    if (unsentSignals(loadFinderEvents()).length > 0)
      void run(null, [], "Reading what you did on the map");
  }, [run]);

  const answer = async (p: FinderProposal, yes: boolean) => {
    setAnswering(p.id);
    setError(null);
    try {
      await decide(auth, p.id, yes ? "accept" : "decline");
      if (yes)
        push({
          at: new Date().toISOString(),
          who: "finder",
          text: `Kept: ${keptLabel(p)}. Code re-ranked your list with it.`,
          by: "policy",
        });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That answer did not go through.");
      await refresh();
    } finally {
      setAnswering(null);
    }
  };

  const react = (pick: FinderPick, kind: "pick" | "pass") => {
    const signal: FinderSignal = {
      kind,
      place_kind: pick.kind,
      has_scan: pick.has_scan,
      rent_from: pick.rent_from ?? null,
      walkup: pick.walkup ?? null,
      parking: pick.parking ?? null,
    };
    setEvents(recordFinderEvent(kind === "pass" ? "passed" : "opened", signalWords(signal)));
    void run(
      null,
      [signal],
      kind === "pass" ? "Learning from your pass" : "Learning from your pick",
    );
  };

  const items: Item[] = [
    ...thread.map((turn) => ({ at: turn.at, type: "turn" as const, turn })),
    ...events
      .filter((e) => e.kind !== "note" && e.kind !== "remembered")
      .map((event) => ({ at: event.at, type: "did" as const, event })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const open = fs.proposals.filter((p) => p.status === "proposed");
  const kept = fs.proposals.filter((p) => p.status === "accepted");
  const lines = learnedLines(fs.learned);

  return (
    <div className="view-body fd-grid">
      <p className="fd-status" data-testid="finder-status">
        <SourceChip source={fs.source} />
        <span>
          {fs.mode === "deepagents"
            ? "Connected. Claude reads what you say and do; code checks every place and number."
            : "Connected, running on our rules: this server has no model key, so code writes every reply."}{" "}
          Nothing it learns applies until you say yes.
        </span>
      </p>

      <section className="fd-panel fd-talk" aria-label="Conversation">
        <h2 className="fd-h">Conversation</h2>
        {items.length === 0 && !busy ? (
          <p className="fd-empty" data-testid="finder-empty">
            Say what matters to you, like &ldquo;under $1,500, no walk-ups&rdquo;. Or pass on a few
            places below or on the <a href="/map">map</a>, and it learns from that.
          </p>
        ) : (
          <ol className="fd-thread" aria-live="polite">
            {items.map((it, i) =>
              it.type === "turn" ? (
                <li
                  key={`t-${it.at}-${i}`}
                  className="fd-msg"
                  data-kind={it.turn.who === "you" ? "note" : "reply"}
                  data-testid={it.turn.who === "you" ? "finder-msg" : "finder-reply"}
                >
                  <span className="fd-kind mono">
                    {it.turn.who === "you" ? "You" : "Finder"}
                    {it.turn.by && (
                      <span className="fd-stamp" data-by={it.turn.by}>
                        {STAMP[it.turn.by]}
                      </span>
                    )}
                  </span>
                  <span className="fd-text">{it.turn.text}</span>
                </li>
              ) : (
                <li
                  key={`d-${it.at}-${i}`}
                  className="fd-did"
                  data-kind={it.event.kind}
                  data-testid="finder-did"
                >
                  {(it.event.signal || it.event.kind === "criteria") && (
                    <span className="fd-did-tag mono">On the map </span>
                  )}
                  {it.event.text}
                </li>
              ),
            )}
          </ol>
        )}

        {busy && (
          <p className="fd-working" role="status" data-testid="finder-working">
            <span className="fd-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            {busy.what}
            {slow ? ". A full run with the model can take about half a minute." : "…"}
          </p>
        )}

        {open.map((p) => (
          <div className="fd-offer" key={p.id} data-testid="finder-proposal">
            <span className="fd-stamp mono" data-by={p.chosen_by}>
              {STAMP[p.chosen_by]}
            </span>
            <p className="fd-offer-text">{p.text}</p>
            <p className="fd-offer-why">Because {p.evidence}.</p>
            <div className="fd-offer-acts">
              <button
                type="button"
                disabled={answering !== null || busy !== null}
                onClick={() => void answer(p, true)}
              >
                Yes
              </button>
              <button
                type="button"
                className="fd-quiet"
                disabled={answering !== null || busy !== null}
                onClick={() => void answer(p, false)}
              >
                Not now
              </button>
            </div>
          </div>
        ))}

        {error && (
          <p className="fd-error" role="alert">
            {error}
          </p>
        )}

        <form
          className="fd-form"
          aria-label="Send a message"
          onSubmit={(e) => {
            e.preventDefault();
            const words = text.trim();
            if (!words || busy) return;
            setText("");
            void run(words, [], "Reading your message and checking the places");
          }}
        >
          <label className="sr-only" htmlFor="finder-note">
            Your message
          </label>
          <textarea
            id="finder-note"
            className="fd-input"
            rows={2}
            maxLength={500}
            value={text}
            placeholder="For example: under $1,500, no walk-ups, near downtown"
            onChange={(e) => setText(e.target.value)}
          />
          <button type="submit" className="fd-send" disabled={!text.trim() || busy !== null}>
            Send
          </button>
        </form>
        <p className="fd-fine">
          Phone numbers, emails, links and street addresses are removed before the model reads your
          words.
        </p>
      </section>

      <section className="fd-panel fd-learned" aria-label="What I've learned about you">
        <h2 className="fd-h">What I&apos;ve learned about you</h2>
        {kept.length === 0 && lines.length === 0 ? (
          <p className="fd-empty" data-testid="learned-empty">
            Nothing yet. It notices what you pick and pass on, and keeps only what you say yes to.
          </p>
        ) : (
          <>
            {kept.length > 0 && (
              <>
                <h3 className="fd-sub mono">Kept, because you said yes</h3>
                <ul className="fd-chips">
                  {kept.map((p) => (
                    <li key={p.id} className="fd-chip fd-chip-kept" data-testid="learned-chip">
                      {keptLabel(p)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {lines.length > 0 && (
              <>
                <h3 className="fd-sub mono">Noticed</h3>
                <ul className="fd-noticed">
                  {lines.map((l) => (
                    <li key={l} data-testid="learned-line">
                      {l}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
        <div className="fd-restart">
          <p className="fd-fine">
            Kept items can&apos;t be removed one by one yet. Start over to clear everything.
          </p>
          <button type="button" className="fd-quiet" onClick={onRestart} disabled={busy !== null}>
            Start over
          </button>
        </div>
      </section>

      <section className="fd-results" aria-label="Leading your list">
        <div className="fd-results-head">
          <h2 className="fd-h">Leading your list</h2>
          <p className="fd-fine">
            Code filters and orders every place. The Finder picks which lead and says why.
          </p>
        </div>
        {fs.picks.length === 0 ? (
          <p className="fd-empty" data-testid="picks-empty">
            {thread.some((t) => t.who === "finder")
              ? "No place fits everything you kept. A higher budget would open more places."
              : "Send a message and the Finder lines up three places here."}
          </p>
        ) : (
          <ol className="fd-picks">
            {fs.picks.map((p) => (
              <PickCard
                key={p.pid}
                pick={p}
                source={fs.source}
                disabled={busy !== null}
                onReact={(kind) => react(p, kind)}
              />
            ))}
          </ol>
        )}
        <HowItDecided trace={fs.trace} />
      </section>
    </div>
  );
}

function PickCard({
  pick,
  source,
  disabled,
  onReact,
}: {
  pick: FinderPick;
  source: FinderState["source"];
  disabled: boolean;
  onReact: (kind: "pick" | "pass") => void;
}) {
  const tags = [
    pick.walkup === true ? "Walk-up" : pick.walkup === false ? "No walk-up" : null,
    pick.parking === true ? "Parking" : pick.parking === false ? "No parking" : null,
  ].filter((t): t is string => Boolean(t));
  const sample = source === "fixture";
  return (
    <li className="fd-pick" data-testid="finder-pick" data-has-scan={pick.has_scan || undefined}>
      <div className="fd-pick-top">
        <span className="fd-rank mono">{String(pick.rank).padStart(2, "0")}</span>
        <span className="fd-stamp mono" data-by={pick.chosen_by}>
          {STAMP[pick.chosen_by]}
        </span>
      </div>
      <p className="fd-pick-line">{pick.line}</p>
      <p className="fd-pick-why">{pick.why}</p>
      {tags.length > 0 && (
        <ul className="fd-tags" aria-label="On record">
          {tags.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      <div className="fd-pick-acts">
        {sample ? (
          <span className="fd-fine" data-testid="pick-sample">
            A sample place made by the team, not on the map.
          </span>
        ) : pick.has_scan ? (
          <a className="fd-link" href={`/tour/${encodeURIComponent(pick.pid)}`}>
            Walk it first
          </a>
        ) : (
          <a className="fd-link" href={`/map?place=${encodeURIComponent(pick.pid)}`}>
            See it on the map
          </a>
        )}
        <span className="fd-pick-react">
          <button
            type="button"
            className="fd-quiet"
            disabled={disabled}
            onClick={() => onReact("pick")}
          >
            I like it
          </button>
          <button
            type="button"
            className="fd-quiet"
            disabled={disabled}
            onClick={() => onReact("pass")}
          >
            Not for me
          </button>
        </span>
      </div>
    </li>
  );
}

const TRACE_TAG: Record<string, string> = {
  todo: "Plan",
  agent: "Hand-off",
  choice: "Pick",
  file: "Note",
  error: "Fallback",
};
const SHOWN_STEPS = 12;

const PROPOSAL_WORDS: Record<string, string> = {
  propose_no_walkup: "skipping walk-ups",
  propose_parking: "only places with parking",
  propose_prefer_scans: "3D-scan places first",
  propose_lower_budget: "a lower budget",
};

function traceLine(e: FinderTraceEvent): string {
  const said = /^The renter said (yes|no) to (\w+)\.$/.exec(e.reason);
  if (said) return `You said ${said[1]} to ${PROPOSAL_WORDS[said[2]!] ?? "the offer"}.`;
  if (e.kind === "choice" && e.pick && PROPOSAL_WORDS[e.pick])
    return `Offered ${PROPOSAL_WORDS[e.pick]}: ${e.reason}`;
  if (e.kind === "agent") return e.reason;
  if (e.kind === "file") return "Wrote its notes for this session.";
  if (e.kind === "choice" && e.pick?.startsWith("lead "))
    return `Lead ${e.pick.slice(5)}: ${e.reason}`;
  return e.reason;
}

export function HowItDecided({ trace }: { trace: FinderTraceEvent[] }) {
  if (trace.length === 0) return null;
  const shown = trace.slice(-SHOWN_STEPS);
  return (
    <details className="fd-how" data-testid="finder-how">
      <summary>
        How the Finder decided <span className="mono fd-fine">{trace.length} steps</span>
      </summary>
      {trace.length > shown.length && (
        <p className="fd-fine">
          The last {shown.length} of {trace.length} steps.
        </p>
      )}
      <ol className="fd-steps">
        {shown.map((e) => (
          <li key={e.seq} className="fd-step" data-kind={e.kind} data-testid="finder-step">
            <span className="fd-step-tag mono">{TRACE_TAG[e.kind] ?? e.kind}</span>
            <span className="fd-step-body">
              <span>{traceLine(e)}</span>
              {e.kind === "todo" && e.options.length > 0 && (
                <ul className="fd-todo">
                  {e.options.map((o, i) => (
                    <li key={i} data-done={o.startsWith("[x]") || undefined}>
                      {o.replace(/^\[[x ]\]\s*/, "")}
                    </li>
                  ))}
                </ul>
              )}
              <span className="fd-step-by mono">{STAMP[e.chosen_by]}</span>
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

// ---------------------------------------------------------------------------------------------
// Offline: no Finder service. Code rules on this device, and the page says so.

function OfflineFinder({ why, onRetry }: { why: "none" | "down"; onRetry: () => void }) {
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
    <div className="view-body fd-grid">
      <section className="fd-panel fd-talk" aria-label="Conversation">
        <h2 className="fd-h">Conversation</h2>
        <p className="fd-honest" data-testid="finder-honest">
          {why === "down"
            ? "The Finder service is not running right now, so nothing answers your messages."
            : "This copy runs without the Finder service, so nothing answers your messages."}{" "}
          Offers here are picked by code on this device and stamped{" "}
          <span className="fd-stamp mono">{OFFER_STAMP}</span>.
          {why === "down" && (
            <>
              {" "}
              <button type="button" className="fd-inline" onClick={onRetry}>
                Try again
              </button>
            </>
          )}
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
          Rent, bedrooms, walk-ups, parking and pets narrow the places below. Anything else is kept
          as your note and does not filter yet.
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
  );
}

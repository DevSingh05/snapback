import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { apiBase, fetchCard } from "../api";
import { STATE_WORD, toneWord } from "../cardStrings";
import { KitArt } from "../components/KitArt";
import { SourceChip } from "../components/SourceChip";
import type {
  Card,
  DataSource,
  FinderPick,
  FinderProposal,
  FinderState,
  PlaceMatch,
  RenterBrief,
} from "../contracts";
import { searchPlaces } from "../search/api";
import { TracePanel } from "../trace";
import {
  decide,
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
} from "../shell/finderApi";
import { MicButton, LevelMeter } from "../shell/FinderPage";
import { markSignalsSent, loadFinderEvents, unsentSignals } from "../shell/finderStore";
import { useVoiceInput, voiceStatus } from "../shell/voice";
import { YourChecks } from "../shell/YourChecks";
import {
  MODE,
  approveChallenge as defaultApprove,
  createCase as defaultCreateCase,
  fetchApiSource,
  getCaseStatus as defaultStatus,
  type ApproveChallenge,
  type CreateCase,
  type GetCaseStatus,
} from "../upload/api";
import { initialState, reduce } from "../upload/machine";
import { MAX_FILES, addFiles, validateSubmission } from "../upload/validate";
import {
  briefFromWords,
  missingFor,
  RENT_REPLIES,
  rentFrom,
  route,
  ROUTE_LINE,
  SWITCH_LABEL,
  switchOf,
  VIEW_HREF,
  VIEW_NAME,
  withoutFacebookLinks,
  type Intent,
  type View,
} from "./intent";
import "./onebox.css";

/** Tap one to start. Each goes through the same routing as typed words. */
export const EXAMPLES = [
  "Paste a Marketplace or Craigslist ad",
  "Find me a 1 bed under $1,500 near downtown",
  "Is this landlord real?",
  "Walk me through a place",
] as const;

export const FB_ASK =
  "Facebook keeps listings behind a login. Paste the listing text here and add its photos, and we'll check it.";

const UNSURE_CHECK = "Check it as an ad";
const UNSURE_FIND = "Find places like this";

const OPEN_LINE: Record<View, string> = {
  map: "See every researched place by where it is.",
  listings: "Browse every researched place as a list.",
  replays: "Real reported scams, replayed step by step.",
  walk: "Places with a 3D scan you can walk before you visit.",
  investigate: "Linked ads, reused photos and payment asks, with the evidence.",
  finder: "What the Finder has learned about you, and why it picked what it did.",
};

type Item =
  | { id: number; type: "you"; text: string; files: string[] }
  | { id: number; type: "route"; intent: Intent; sub: { text: string; files: File[] } | null }
  | {
      id: number;
      type: "bot";
      text: string;
      by: "model" | "policy";
      replies?: readonly string[];
      onReply?: "rent" | "send" | "unsure";
    }
  | {
      id: number;
      type: "check";
      input: { link: string | null; text: string | null; files: File[] };
    }
  | { id: number; type: "places"; brief: RenterBrief; scansOnly: boolean; note: string }
  | { id: number; type: "picks"; picks: FinderPick[]; source: DataSource }
  | { id: number; type: "offer"; proposal: FinderProposal }
  | { id: number; type: "open"; view: View }
  | { id: number; type: "error"; text: string };

type ItemInput = Item extends infer T ? (T extends Item ? Omit<T, "id"> : never) : never;

interface Props {
  createCase?: CreateCase;
  approveChallenge?: ApproveChallenge;
  getCaseStatus?: GetCaseStatus;
  pollMs?: number;
  checkingMs?: number;
  waitingMs?: number;
  mode?: DataSource;
}

// Home: one box. Type, talk, paste a link or an ad, or drop screenshots. Code reads what you
// meant (intent.ts), says so in one line with a switch, and the answer lands in the thread as a
// card: the verdict, the places, the walk. Missing details are asked here, never with a form.
export function OneBox(props: Props) {
  const mode = props.mode ?? MODE;
  const [items, setItems] = useState<Item[]>([]);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileErrors, setFileErrors] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [cases, setCases] = useState<string[]>([]);
  const [knownRent, setKnownRent] = useState<number | null>(null);
  const [pendingWish, setPendingWish] = useState<string | null>(null);
  const [unsureWords, setUnsureWords] = useState<string | null>(null);
  const [fs, setFs] = useState<FinderState | null>(null);
  const [apiSource, setApiSource] = useState<DataSource>("fixture");
  const nextId = useRef(1);
  const auth = useRef<FinderAuth | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mode !== "live") return;
    const ctrl = new AbortController();
    fetchApiSource(ctrl.signal)
      .then(setApiSource)
      .catch(() => {});
    return () => ctrl.abort();
  }, [mode]);
  const shownMode: DataSource = mode === "live" ? apiSource : mode;

  const add = useCallback((...next: ItemInput[]) => {
    setItems((prev) => [...prev, ...next.map((n) => ({ ...n, id: nextId.current++ }) as Item)]);
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [items.length, busy]);

  // --- The Finder: one session for this tab, opened the first time it is needed.
  const finder = useCallback(async (): Promise<FinderAuth | null> => {
    if (!apiBase()) return null;
    if (auth.current) return auth.current;
    const saved = loadAuth();
    if (saved) {
      try {
        setFs(await getState(saved));
        auth.current = saved;
        return saved;
      } catch (err) {
        if (!(err instanceof FinderGone)) throw err;
        saveAuth(null);
      }
    }
    const fresh = await startSession();
    auth.current = { sid: fresh.sid, token: fresh.token };
    setFs(await getState(auth.current));
    return auth.current;
  }, []);

  /** Words for the Finder. Offline, code reads the words and lists places, and says so. */
  const askFinder = useCallback(
    async (words: string, asWish: boolean) => {
      setBusy(asWish ? "Finding places that fit" : "Thinking about your question");
      try {
        const a = await finder();
        if (!a) throw new FinderOffline("No API is configured.");
        const signals = unsentSignals(loadFinderEvents());
        const reply = await sendMessage(a, words, signals);
        if (signals.length) markSignalsSent();
        const state = await getState(a).catch(() => null);
        if (state) setFs(state);
        const picks = (state?.picks ?? reply.picks).slice(0, 3);
        const offers = (state?.proposals ?? reply.proposals).filter((p) => p.status === "proposed");
        add(
          { type: "bot", text: reply.reply, by: reply.reply_by },
          ...(asWish && picks.length
            ? [{ type: "picks" as const, picks, source: reply.source }]
            : []),
          ...offers.slice(0, 1).map((proposal) => ({ type: "offer" as const, proposal })),
        );
      } catch (err) {
        if (err instanceof FinderOffline || err instanceof FinderGone) {
          auth.current = null;
          if (asWish)
            add({
              type: "places",
              brief: briefFromWords(words),
              scansOnly: false,
              note: apiBase()
                ? "The Finder is not running right now, so code read your words and listed these."
                : "Code read your words and listed these. The Finder agent runs when the app is connected to the API.",
            });
          else
            add({
              type: "bot",
              by: "policy",
              text: "The Finder is not running right now, so nothing can answer questions. Open the full result for every check and what it means.",
            });
        } else {
          add({
            type: "error",
            text: err instanceof Error ? err.message : "The Finder could not answer.",
          });
        }
      } finally {
        setBusy(null);
      }
    },
    [add, finder],
  );

  const findWith = useCallback(
    (wish: string) => {
      const rent = rentFrom(wish);
      if (rent) setKnownRent(rent);
      void askFinder(wish, true);
    },
    [askFinder],
  );

  /** Runs one submission with a known intent. */
  const run = useCallback(
    (intent: Intent, words: string, attached: File[]) => {
      if (intent.kind === "check-fb") {
        add({ type: "bot", by: "policy", text: FB_ASK });
        box.current?.focus();
        return;
      }
      if (intent.kind === "check") {
        // A Facebook address is never sent or fetched: only the pasted words and photos are.
        const v = validateSubmission({ text: withoutFacebookLinks(words), files: attached });
        if (!v.ok) {
          add({ type: "bot", by: "policy", text: v.error });
          return;
        }
        add({ type: "check", input: { link: v.link, text: v.text, files: v.files } });
        return;
      }
      if (intent.kind === "check-ask") {
        add({
          type: "bot",
          by: "policy",
          text: "Paste the ad's link or its text here, or add screenshots of it. For Facebook Marketplace, paste the text and add its photos. I'll check the place, the person and the price.",
        });
        box.current?.focus();
        return;
      }
      if (intent.kind === "open") {
        if (intent.view === "walk")
          add({
            type: "places",
            brief: {},
            scansOnly: true,
            note: "These have a 3D scan on record. Pick one to walk it, room by room.",
          });
        else add({ type: "open", view: intent.view });
        return;
      }
      if (intent.kind === "unsure") {
        setUnsureWords(words);
        add({
          type: "bot",
          by: "policy",
          text: "Is this an ad you want checked, or a description of what you're looking for?",
          replies: [UNSURE_CHECK, UNSURE_FIND],
          onReply: "unsure",
        });
        return;
      }
      if (intent.kind === "ask") {
        void askFinder(words, false);
        return;
      }
      // find
      if (missingFor(words, knownRent) === "max_rent") {
        setPendingWish(words);
        add({
          type: "bot",
          by: "policy",
          text: "What's your max rent a month?",
          replies: RENT_REPLIES,
          onReply: "rent",
        });
        return;
      }
      findWith(words);
    },
    [add, askFinder, findWith, knownRent],
  );

  const answerRent = useCallback(
    (reply: string) => {
      const wish = pendingWish ?? "Find me a place";
      setPendingWish(null);
      add({ type: "you", text: reply, files: [] });
      const n = rentFrom(reply);
      if (n) setKnownRent(n);
      findWith(n ? `${wish}, under $${n.toLocaleString("en-US")}` : `${wish}, no budget limit`);
    },
    [add, findWith, pendingWish],
  );

  const answerUnsure = useCallback(
    (reply: string) => {
      const words = unsureWords ?? "";
      setUnsureWords(null);
      add({ type: "you", text: reply, files: [] });
      run(reply === UNSURE_CHECK ? { kind: "check" } : { kind: "find" }, words, []);
    },
    [add, unsureWords, run],
  );

  const submit = useCallback(
    (raw: string, attached: File[] = files) => {
      const words = raw.trim();
      if (!words && attached.length === 0) {
        setError("Type or say what you need, paste an ad, or add screenshots.");
        return;
      }
      if (busy) return;
      setError(null);
      setFileErrors([]);
      // An open question for the budget takes a typed amount as its answer.
      if (pendingWish && attached.length === 0 && rentFrom(words) !== null && words.length < 40) {
        setText("");
        answerRent(words);
        return;
      }
      const intent = route({ text: words, files: attached.length, caseOnScreen: cases.length > 0 });
      add(
        { type: "you", text: words, files: attached.map((f) => f.name) },
        { type: "route", intent, sub: { text: words, files: attached } },
      );
      setText("");
      setFiles([]);
      run(intent, words, attached);
    },
    [add, answerRent, busy, cases.length, files, pendingWish, run],
  );

  const reroute = (routeId: number, to: Intent) => {
    const it = items.find((i) => i.id === routeId);
    if (!it || it.type !== "route" || !it.sub) return;
    const sub = it.sub;
    setItems((prev) =>
      prev.map((i) =>
        i.id === routeId && i.type === "route" ? { ...i, intent: to, sub: null } : i,
      ),
    );
    run(to, sub.text, sub.files);
  };

  function take(list: FileList | File[] | null) {
    if (!list || list.length === 0) return;
    const r = addFiles(files, Array.from(list));
    setFiles(r.files);
    setFileErrors(r.errors);
    setError(null);
  }

  // --- Voice: the Finder's mic. What you say is sent as soon as it is written down.
  const [stt, setStt] = useState(true);
  useEffect(() => {
    let on = true;
    void voiceStatus().then((s) => on && setStt(s.stt));
    return () => {
      on = false;
    };
  }, []);
  const submitRef = useRef(submit);
  useEffect(() => {
    submitRef.current = submit;
  });
  const voice = useVoiceInput({
    server: stt,
    onWords: (words) => submitRef.current(words),
    onSilence: () => setError("I didn't catch that. Hold the mic and try again."),
  });

  const empty = items.length === 0;
  const kept = fs?.proposals.filter((p) => p.status === "accepted") ?? [];
  const lines = fs ? learnedLines(fs.learned) : [];

  const composer = (
    <Composer
      text={text}
      setText={(v) => {
        setText(v);
        setError(null);
      }}
      files={files}
      setFiles={setFiles}
      take={take}
      dragging={dragging}
      setDragging={setDragging}
      onSend={() => submit(text)}
      busy={busy !== null}
      voice={voice}
      fileInput={fileInput}
      box={box}
      big={empty}
    />
  );

  return (
    <div className="ob" data-empty={empty || undefined} data-testid="one-box">
      {!empty && (
        <div className="ob-top">
          <SourceChip source={shownMode} />
          <div className="ob-top-acts">
            <button
              type="button"
              className="ob-quiet"
              onClick={() => {
                setItems([]);
                setCases([]);
                setPendingWish(null);
                setUnsureWords(null);
                setError(null);
              }}
            >
              New conversation
            </button>
          </div>
        </div>
      )}

      {empty ? (
        <section className="ob-start" aria-labelledby="ob-title">
          <h1 id="ob-title" className="ob-title">
            Found a place online? Ask before you pay.
          </h1>
          <p className="ob-lead">
            Paste the ad or its link, add a screenshot, or just say what you&apos;re looking for.
          </p>
          {composer}
          {(error || fileErrors.length > 0) && <Problems error={error} fileErrors={fileErrors} />}
          <ul className="ob-examples" aria-label="Try one">
            {EXAMPLES.map((ex) => (
              <li key={ex}>
                <button type="button" className="ob-example" onClick={() => submit(ex, [])}>
                  {ex}
                </button>
              </li>
            ))}
          </ul>
          <WhatYouCanDo onAsk={(w) => submit(w, [])} />
          <p className="ob-fine ob-honest">
            <SourceChip source={shownMode} />
            <span>
              SNAPBACK never messages anyone for you. Code sets every verdict; a model only explains
              it.
            </span>
          </p>
          <YourChecks />
        </section>
      ) : (
        <>
          <ol className="ob-thread" aria-live="polite" aria-label="Conversation">
            {items.map((it) => (
              <ThreadItem
                key={it.id}
                it={it}
                mode={mode}
                props={props}
                onSwitch={(to) => reroute(it.id, to)}
                onReply={(r, kind) =>
                  kind === "rent"
                    ? answerRent(r)
                    : kind === "unsure"
                      ? answerUnsure(r)
                      : submit(r, [])
                }
                onCase={(id) => setCases((c) => (c.includes(id) ? c : [...c, id]))}
                onFollow={(words) => submit(words, [])}
                onDecided={async (p, yes) => {
                  if (!auth.current) return;
                  try {
                    await decide(auth.current, p.id, yes ? "accept" : "decline");
                    setFs(await getState(auth.current));
                    if (yes)
                      add({
                        type: "bot",
                        by: "policy",
                        text: `Kept: ${keptLabel(p)}. Your next places are ranked with it.`,
                      });
                  } catch (err) {
                    add({
                      type: "error",
                      text: err instanceof Error ? err.message : "That answer did not go through.",
                    });
                  }
                }}
              />
            ))}
            {busy && (
              <li className="ob-working" role="status" data-testid="ob-working">
                <span className="ob-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                {busy}…
              </li>
            )}
          </ol>
          <div ref={end} />
          <div className="ob-dock">
            {(error || fileErrors.length > 0) && <Problems error={error} fileErrors={fileErrors} />}
            {composer}
            <Learned kept={kept.map(keptLabel)} noticed={lines} />
          </div>
        </>
      )}
    </div>
  );
}

/** The sample ad: synthetic, written by the team, with the red flags a real one carries. */
export const SAMPLE_AD =
  "2 bed 2 bath near downtown, $1,350/month, utilities included. I'm working abroad so I can't " +
  "show it, but send the $600 deposit by Zelle today and I'll mail you the keys.";

// What the box can do, each shown with a piece of the real product and one tap to try it.
function WhatYouCanDo({ onAsk }: { onAsk: (words: string) => void }) {
  return (
    <section className="ob-can" aria-labelledby="ob-can-title">
      <h2 id="ob-can-title" className="ob-can-title">
        What you can do here
      </h2>
      <ul className="ob-can-list">
        <li>
          <button type="button" className="ob-can-item" onClick={() => onAsk(SAMPLE_AD)}>
            <span className="ob-can-shot ob-shot-verdict" aria-hidden="true">
              <span className="ob-shot-kicker">Case 7Q2M</span>
              <span className="ob-shot-word">Hold off for now</span>
              <span className="ob-shot-line">
                <span>Payment ask</span>
                <span className="ob-tone" data-tone="warn">
                  Warning
                </span>
              </span>
              <span className="ob-shot-line">
                <span>Real photos</span>
                <span className="ob-tone" data-tone="ok">
                  Matches
                </span>
              </span>
            </span>
            <span className="ob-can-name">Check an ad</span>
            <span className="ob-can-line">Try it on our sample ad</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="ob-can-item"
            onClick={() => onAsk("Find me a 1 bed near downtown")}
          >
            <span className="ob-can-shot ob-shot-ask" aria-hidden="true">
              <span className="ob-shot-q">What&apos;s your max rent a month?</span>
              <span className="ob-shot-chips">
                <span>$1,200</span>
                <span>$1,500</span>
                <span>$2,000</span>
              </span>
            </span>
            <span className="ob-can-name">Find a place</span>
            <span className="ob-can-line">Say what you want; it asks the rest</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="ob-can-item"
            onClick={() => onAsk("Walk me through a place")}
          >
            <span className="ob-can-shot ob-shot-walk" aria-hidden="true">
              <KitArt kind="scan" className="ob-shot-art" detail="low" />
            </span>
            <span className="ob-can-name">Walk it first</span>
            <span className="ob-can-line">See it room by room before you visit</span>
          </button>
        </li>
      </ul>
      <nav className="ob-also" aria-label="Or open">
        <span>Or open</span>
        <a href="/map">Map</a>
        <a href="/listings">Listings</a>
        <a href="/finder">Finder</a>
        <a href="/replay">Replays</a>
        <a href="/investigate">Investigate</a>
      </nav>
    </section>
  );
}

/** What the Finder has learned, as one quiet line under the box. The detail is in the Finder. */
function Learned({ kept, noticed }: { kept: string[]; noticed: string[] }) {
  const all = [...kept, ...noticed];
  return (
    <p className="ob-learned" data-testid="ob-learned">
      {all.length === 0 ? (
        <span>It learns from what you pick and pass on, and keeps only what you say yes to.</span>
      ) : (
        <span>
          Learned: {all.slice(0, 3).join(" · ")}
          {all.length > 3 ? ` and ${all.length - 3} more` : ""}.
        </span>
      )}{" "}
      <a href="/finder">See it in the Finder</a>
    </p>
  );
}

function Problems({ error, fileErrors }: { error: string | null; fileErrors: string[] }) {
  return (
    <div className="ob-problems" role="alert">
      {error && <p>{error}</p>}
      {fileErrors.map((m) => (
        <p key={m}>{m}</p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// The box itself.

function Glyph({ name }: { name: "attach" | "send" | "x" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="square"
      aria-hidden="true"
    >
      {name === "attach" ? (
        <path d="M16.5 7.5 9 15a2.1 2.1 0 0 0 3 3l8-8a4.2 4.2 0 0 0-6-6l-8.5 8.5a6.4 6.4 0 0 0 9 9L20 16" />
      ) : name === "send" ? (
        <path d="M12 19V5M6 11l6-6 6 6" />
      ) : (
        <path d="M7 7l10 10M17 7 7 17" />
      )}
    </svg>
  );
}

function Composer({
  text,
  setText,
  files,
  setFiles,
  take,
  dragging,
  setDragging,
  onSend,
  busy,
  voice,
  fileInput,
  box,
  big,
}: {
  text: string;
  setText: (v: string) => void;
  files: File[];
  setFiles: (f: File[]) => void;
  take: (l: FileList | File[] | null) => void;
  dragging: boolean;
  setDragging: (d: boolean) => void;
  onSend: () => void;
  busy: boolean;
  voice: ReturnType<typeof useVoiceInput>;
  fileInput: React.RefObject<HTMLInputElement | null>;
  box: React.RefObject<HTMLTextAreaElement | null>;
  big: boolean;
}) {
  const recording = voice.state === "recording";
  const writing = voice.state === "writing";
  // The box grows with what is pasted, up to a limit, then scrolls.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, big ? 320 : 220)}px`;
  }, [text, big, box]);
  return (
    <form
      className="ob-box"
      data-big={big || undefined}
      data-dragging={dragging || undefined}
      aria-label="Ask SNAPBACK"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        take(e.dataTransfer.files);
      }}
    >
      <label htmlFor="listing" className="sr-only">
        Paste an ad, a link, or say what you need
      </label>
      {recording || writing ? (
        <div className="ob-listen" role="status" data-testid="voice-listening">
          {recording ? (
            <>
              {voice.engine === "eleven" && <LevelMeter level={voice.level} />}
              <span>
                <span className="ob-listen-word">Listening</span>{" "}
                {voice.engine === "browser" && voice.interim
                  ? voice.interim
                  : "Let go of the mic, or tap it, to send."}
              </span>
              <button
                type="button"
                className="ob-icon"
                aria-label="Cancel, don't send"
                onClick={() => voice.cancel()}
              >
                <Glyph name="x" />
              </button>
            </>
          ) : (
            <span>Writing down what you said…</span>
          )}
        </div>
      ) : (
        <textarea
          id="listing"
          ref={box}
          className="ob-input"
          rows={big ? 2 : 1}
          value={text}
          placeholder={
            big
              ? "Paste an ad or link, or type: a 1 bed under $1,500 near downtown"
              : "Ask a follow-up, paste another ad, or say what you want"
          }
          autoComplete="off"
          spellCheck
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => {
            const pasted = Array.from(e.clipboardData?.files ?? []);
            if (pasted.length) {
              e.preventDefault();
              take(pasted);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSend();
            }
          }}
        />
      )}
      {files.length > 0 && (
        <ul className="ob-files" aria-label="Added screenshots">
          {files.map((f) => (
            <li key={`${f.name}-${f.size}`}>
              <span>{f.name}</span>
              <button
                type="button"
                aria-label={`Remove ${f.name}`}
                onClick={() => setFiles(files.filter((g) => g !== f))}
              >
                <Glyph name="x" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="ob-bar">
        <input
          ref={fileInput}
          id="photos"
          type="file"
          className="sr-only"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
          multiple
          tabIndex={-1}
          onChange={(e) => {
            take(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="ob-tool"
          onClick={() => fileInput.current?.click()}
          title={`Screenshots or photos, up to ${MAX_FILES}`}
        >
          <Glyph name="attach" />
          <span>Add screenshots</span>
        </button>
        <span className="ob-bar-fill" />
        {voice.engine && (
          <span className="ob-mic">
            <MicButton voice={voice} disabled={busy} onOpen={() => undefined} />
            <span className="ob-mic-label" aria-hidden="true">
              {recording ? "Tap to send" : "Hold to talk"}
            </span>
          </span>
        )}
        <button
          type="submit"
          className="ob-send"
          disabled={busy || recording || writing || (!text.trim() && files.length === 0)}
        >
          <span>Send</span>
          <Glyph name="send" />
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------------------------
// The thread.

function ThreadItem({
  it,
  mode,
  props,
  onSwitch,
  onReply,
  onCase,
  onFollow,
  onDecided,
}: {
  it: Item;
  mode: DataSource;
  props: Props;
  onSwitch: (to: Intent) => void;
  onReply: (reply: string, kind: "rent" | "send" | "unsure") => void;
  onCase: (id: string) => void;
  onFollow: (words: string) => void;
  onDecided: (p: FinderProposal, yes: boolean) => Promise<void>;
}) {
  switch (it.type) {
    case "you":
      return (
        <li className="ob-you" data-testid="ob-you">
          {it.text && <p>{it.text}</p>}
          {it.files.length > 0 && (
            <p className="ob-you-files">
              {it.files.length} screenshot{it.files.length === 1 ? "" : "s"}: {it.files.join(", ")}
            </p>
          )}
        </li>
      );
    case "route": {
      const other = it.sub ? switchOf(it.intent) : null;
      const label =
        it.intent.kind === "open"
          ? `Opening ${VIEW_NAME[it.intent.view]}`
          : ROUTE_LINE[it.intent.kind];
      return (
        <li className="ob-route" data-testid="ob-route" data-intent={it.intent.kind}>
          <span className="ob-route-mark" aria-hidden="true" />
          <span>{label}</span>
          {other && (
            <button
              type="button"
              className="ob-route-switch"
              data-testid="ob-switch"
              onClick={() => onSwitch(other)}
            >
              Not right? {SWITCH_LABEL[other.kind]}
            </button>
          )}
        </li>
      );
    }
    case "bot":
      return (
        <li className="ob-bot" data-testid="ob-bot">
          <p>{it.text}</p>
          <span className="ob-stamp" data-by={it.by}>
            {STAMP[it.by]}
          </span>
          {it.replies && (
            <ul className="ob-replies" aria-label="Quick replies">
              {it.replies.map((r) => (
                <li key={r}>
                  <button type="button" onClick={() => onReply(r, it.onReply ?? "send")}>
                    {r}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </li>
      );
    case "error":
      return (
        <li className="ob-bot ob-bot-error" role="alert">
          <p>{it.text}</p>
        </li>
      );
    case "check":
      return (
        <li className="ob-card-row">
          <CheckRun
            input={it.input}
            mode={mode}
            props={props}
            onCase={onCase}
            onFollow={onFollow}
          />
        </li>
      );
    case "places":
      return (
        <li className="ob-card-row">
          <PlacesCard brief={it.brief} scansOnly={it.scansOnly} note={it.note} />
        </li>
      );
    case "picks":
      return (
        <li className="ob-card-row">
          <PicksCard picks={it.picks} source={it.source} />
        </li>
      );
    case "offer":
      return (
        <li className="ob-card-row">
          <OfferCard proposal={it.proposal} onDecided={onDecided} />
        </li>
      );
    case "open":
      return (
        <li className="ob-card-row">
          <article className="ob-card ob-open" data-testid="ob-open">
            <p className="ob-card-kicker">{VIEW_NAME[it.view]}</p>
            <p className="ob-card-text">{OPEN_LINE[it.view]}</p>
            <a className="ob-primary" href={VIEW_HREF[it.view]}>
              Open {VIEW_NAME[it.view]}
            </a>
          </article>
        </li>
      );
  }
}

// --- The ad check, inline. The same steps and approval gate as before, as one card.

const STEPS = [
  { key: "reading", label: "Reading the ad" },
  { key: "checking", label: "Checking the building" },
  { key: "approval", label: "Your OK to ask the poster" },
  { key: "waiting", label: "Waiting for the poster" },
] as const;

function CheckRun({
  input,
  mode,
  props,
  onCase,
  onFollow,
}: {
  input: { link: string | null; text: string | null; files: File[] };
  mode: DataSource;
  props: Props;
  onCase: (id: string) => void;
  onFollow: (words: string) => void;
}) {
  const {
    createCase = defaultCreateCase,
    approveChallenge = defaultApprove,
    getCaseStatus = defaultStatus,
    pollMs = 700,
    checkingMs = 900,
    waitingMs = 1800,
  } = props;
  const [state, dispatch] = useReducer(reduce, initialState);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);
  const deciding = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    dispatch({ type: "submit" });
    createCase(input)
      .then((made) =>
        dispatch({
          type: "created",
          caseId: made.case_id,
          challengeText: made.challenge_text,
          source: made.source,
        }),
      )
      .catch((err: unknown) =>
        dispatch({
          type: "fail",
          message: err instanceof Error ? err.message : "Something went wrong. Try again.",
        }),
      );
  }, [createCase, input]);

  useEffect(() => {
    if (state.step !== "checking") return;
    const t = setTimeout(() => dispatch({ type: "checked" }), mode === "fixture" ? checkingMs : 0);
    return () => clearTimeout(t);
  }, [state.step, checkingMs, mode]);

  useEffect(() => {
    if (state.step !== "waiting" || mode !== "fixture") return;
    const t = setTimeout(() => dispatch({ type: "done" }), waitingMs);
    return () => clearTimeout(t);
  }, [state.step, waitingMs, mode]);

  const waitingCase = state.step === "waiting" ? state.caseId : null;
  useEffect(() => {
    if (waitingCase === null || mode !== "live") return;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const s = await getCaseStatus(waitingCase, ctrl.signal);
        if (s.status === "done") {
          dispatch({ type: "done" });
          return;
        }
      } catch {
        if (ctrl.signal.aborted) return;
      }
      timer = setTimeout(poll, pollMs);
    };
    void poll();
    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [waitingCase, mode, getCaseStatus, pollMs]);

  const doneCase = state.step === "done" ? state.caseId : null;
  useEffect(() => {
    if (doneCase) onCase(doneCase);
  }, [doneCase, onCase]);

  async function choose(decision: "send" | "cancel") {
    if (state.step !== "approval" || deciding.current) return;
    deciding.current = true;
    setBusy(true);
    if (mode === "live") {
      try {
        await approveChallenge(state.caseId, decision);
      } catch (err) {
        deciding.current = false;
        setBusy(false);
        dispatch({
          type: "fail",
          message: err instanceof Error ? err.message : "Something went wrong. Try again.",
        });
        return;
      }
    }
    deciding.current = false;
    setBusy(false);
    dispatch({ type: decision === "send" ? "approve" : "skip" });
  }

  if (state.step === "done")
    return <VerdictCard caseId={state.caseId} source={state.source} onFollow={onFollow} />;

  if (state.step === "error")
    return (
      <article className="ob-card" data-tone="mismatch" data-testid="ob-check-error">
        <p className="ob-card-kicker">That did not go through</p>
        <p className="ob-card-text" role="alert">
          {state.message}
        </p>
        <p className="ob-muted">Nothing was sent. Paste it again to retry.</p>
      </article>
    );

  const active = STEPS.findIndex((s) => s.key === state.step);
  const source: DataSource = "source" in state ? state.source : mode;
  return (
    <article className="ob-card ob-check" data-testid="ob-check">
      <header className="ob-card-head">
        <p className="ob-card-kicker">Checking the ad</p>
        <SourceChip source={source} />
      </header>
      <ol className="ob-steps" aria-label="Progress">
        {STEPS.map((s, i) => {
          const status = i < active ? "done" : i === active ? "active" : "todo";
          return (
            <li
              key={s.key}
              data-status={status}
              aria-current={status === "active" ? "step" : undefined}
            >
              {s.label}
              <span className="sr-only">
                {status === "done" ? " (done)" : status === "active" ? " (now)" : " (next)"}
              </span>
            </li>
          );
        })}
      </ol>
      {state.step === "approval" && (
        <section className="ob-approve" aria-labelledby="ob-approve-title">
          <h2 id="ob-approve-title" className="ob-card-title">
            Ask the poster for proof
          </h2>
          <p className="ob-card-text">
            A real landlord can send a fresh photo from inside the unit. Copy this and send it
            yourself. Nothing is sent for you.
          </p>
          <label htmlFor="challenge" className="sr-only">
            Message to send
          </label>
          <textarea
            id="challenge"
            className="ob-message"
            rows={4}
            readOnly
            value={state.challengeText}
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="ob-acts">
            <button
              type="button"
              className="ob-primary"
              disabled={busy}
              onClick={() => void choose("send")}
            >
              I approve it and I will send it
            </button>
            <button
              type="button"
              className="ob-secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(state.challengeText);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
            >
              {copied ? "Copied" : "Copy message"}
            </button>
            <button
              type="button"
              className="ob-quiet"
              disabled={busy}
              onClick={() => void choose("cancel")}
            >
              Skip this, show the result
            </button>
          </div>
        </section>
      )}
      {state.step === "waiting" && (
        <div className="ob-wait">
          <p className="ob-card-text">
            No reply yet means hold off, not a failure. The result updates when they answer.
          </p>
          {mode === "live" && <TracePanel caseId={state.caseId} mode="live" />}
          <button type="button" className="ob-secondary" onClick={() => dispatch({ type: "done" })}>
            See my result now
          </button>
        </div>
      )}
    </article>
  );
}

const TONE_OF: Record<Card["state"], string> = {
  dont_pay: "mismatch",
  hold: "warn",
  unverified: "unchecked",
  verified: "ok",
};

const WORD_TONE: Record<string, string> = {
  Matches: "ok",
  "Doesn't match": "mismatch",
  Warning: "warn",
  "Not confirmed": "unconfirmed",
  "Not checked": "unchecked",
};

const FIRST_LINES = 3;

const ROW_NAME = { place: "Place", person: "Person", price: "Price", claims: "Ad claims" } as const;

export function VerdictCard({
  caseId,
  source,
  onFollow,
}: {
  caseId: string;
  source: DataSource;
  onFollow?: (words: string) => void;
}) {
  const [card, setCard] = useState<Card | null | "error">(null);
  useEffect(() => {
    const ctrl = new AbortController();
    fetchCard(caseId, ctrl.signal)
      .then(setCard)
      .catch(() => !ctrl.signal.aborted && setCard("error"));
    return () => ctrl.abort();
  }, [caseId]);
  const [all, setAll] = useState(false);
  const id = encodeURIComponent(caseId);
  if (card === null)
    return (
      <article className="ob-card" data-testid="ob-verdict-wait">
        <p className="ob-muted">Loading the result for case {caseId}…</p>
      </article>
    );
  if (card === "error")
    return (
      <article className="ob-card" data-testid="ob-verdict">
        <p className="ob-card-text">The result is ready but did not load here.</p>
        <a className="ob-primary" href={`/case/${id}`}>
          Open the result
        </a>
      </article>
    );
  const allLines = card.rows.flatMap((row) =>
    row.lines.map((line, i) => ({ kind: row.kind, line, first: i === 0, key: `${row.kind}-${i}` })),
  );
  // Answer first: the lines that most need attention, then the rest one tap below.
  const order = (t: string) => ({ red_flag: 0, hold: 1, not_shown: 1, ok: 2 })[t] ?? 3;
  const shownLines = all
    ? allLines
    : [...allLines]
        .sort((a, b) => order(a.line.tone) - order(b.line.tone))
        .slice(0, FIRST_LINES)
        .map((l, i, list) => ({ ...l, first: i === 0 || list[i - 1]!.kind !== l.kind }));
  return (
    <article
      className="ob-card ob-verdict"
      data-tone={TONE_OF[card.state]}
      data-testid="ob-verdict"
    >
      <header className="ob-card-head">
        <p className="ob-card-kicker">
          Case <span className="mono">{card.case_id}</span>
        </p>
        <SourceChip source={card.source ?? source} />
      </header>
      <h2 className="ob-verdict-word">{STATE_WORD[card.state]}</h2>
      <p className="ob-muted">Code set this verdict from the checks below.</p>
      <dl className="ob-lines">
        {shownLines.map(({ kind, line, first, key }) => {
          const word = toneWord(line.tone, kind);
          return (
            <div key={key} className="ob-line">
              <dt>
                <span className="ob-line-kind">{first ? ROW_NAME[kind] : ""}</span>
                <span className="ob-line-label">{line.label}</span>
              </dt>
              <dd>
                <span className="ob-line-text">{line.text}</span>
                <span className="ob-tone" data-tone={WORD_TONE[word] ?? "unchecked"}>
                  {word}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>
      {allLines.length > FIRST_LINES && (
        <button type="button" className="ob-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `How we know: all ${allLines.length} checks`}
        </button>
      )}
      <p className="ob-muted">Not checked: {card.not_checked.join(", ")}.</p>
      <div className="ob-acts">
        <a className="ob-primary" href={`/case/${id}`}>
          Open the full result
        </a>
        <a className="ob-secondary" href={`/case/${id}/twin`} data-testid="ob-walk">
          Walk it first
        </a>
        <a className="ob-quiet" href={`/case/${id}/prep`}>
          Get ready to visit
        </a>
      </div>
      {onFollow && (
        <ul className="ob-replies ob-follow" aria-label="Next">
          {["Find me safer places like this", "Show me on the map", "Replay a real case"].map(
            (w) => (
              <li key={w}>
                <button type="button" onClick={() => onFollow(w)}>
                  {w}
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </article>
  );
}

// --- Places, inline: three at most, each with its one next step.

function tourHref(p: PlaceMatch): string {
  const q = p.plan_key ? `?plan_key=${encodeURIComponent(p.plan_key)}` : "";
  return `/tour/${encodeURIComponent(p.property_id)}${q}`;
}

function briefWords(b: RenterBrief): string {
  const bits = [
    b.beds_min != null ? (b.beds_min === 0 ? "studio" : `${b.beds_min}+ bed`) : null,
    b.max_rent_month ? `under $${b.max_rent_month.toLocaleString("en-US")}` : null,
    b.needs_no_walkup ? "no walk-ups" : null,
    b.needs_parking ? "parking" : null,
    b.pets ? "pets" : null,
  ].filter(Boolean);
  return bits.length ? bits.join(", ") : "any budget";
}

function PlacesCard({
  brief,
  scansOnly,
  note,
}: {
  brief: RenterBrief;
  scansOnly: boolean;
  note: string;
}) {
  const [load, setLoad] = useState<
    | { s: "loading" }
    | {
        s: "ready";
        matches: PlaceMatch[];
        source: DataSource;
        asOf: string;
        tradeoff: string | null;
      }
    | { s: "error"; message: string }
  >({ s: "loading" });
  const key = JSON.stringify(brief);
  useEffect(() => {
    const ctrl = new AbortController();
    searchPlaces(brief, ctrl.signal)
      .then((p) =>
        setLoad({
          s: "ready",
          matches: p.matches.filter((m) => !scansOnly || m.has_3d_scan),
          source: p.source,
          asOf: p.as_of,
          tradeoff: p.tradeoff_question,
        }),
      )
      .catch(
        (err: unknown) =>
          !ctrl.signal.aborted &&
          setLoad({ s: "error", message: err instanceof Error ? err.message : "Try again." }),
      );
    return () => ctrl.abort();
    // key is the stable form of brief
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, scansOnly]);
  const shown = load.s === "ready" ? load.matches.slice(0, 3) : [];
  return (
    <article className="ob-card ob-places" data-testid="ob-places">
      <header className="ob-card-head">
        <p className="ob-card-kicker">
          {scansOnly ? "Places you can walk first" : `Places for ${briefWords(brief)}`}
        </p>
        {load.s === "ready" && <SourceChip source={load.source} />}
      </header>
      <p className="ob-muted">{note}</p>
      {load.s === "loading" && <p className="ob-muted">Looking up researched places…</p>}
      {load.s === "error" && (
        <p className="ob-card-text" role="alert">
          Places did not load. {load.message}
        </p>
      )}
      {load.s === "ready" && shown.length === 0 && (
        <p className="ob-card-text" data-testid="ob-places-empty">
          {load.tradeoff ??
            "Nothing on record fits all of that. A higher budget opens more places."}
        </p>
      )}
      {shown.length > 0 && (
        <ol className="ob-picks">
          {shown.map((p, i) => (
            <li
              key={`${p.property_id}-${p.plan_key ?? i}`}
              className="ob-pick"
              data-testid="ob-pick"
            >
              <span className="ob-rank mono">{i + 1}</span>
              <div className="ob-pick-body">
                <p className="ob-pick-line">
                  {p.floor_plan ?? (p.kind === "house" ? "House" : "Apartment")}
                </p>
                <p className="ob-muted">{p.price_text}</p>
                <span className="ob-stamp" data-by="policy">
                  {STAMP.policy}
                </span>
              </div>
              {p.has_3d_scan ? (
                <a className="ob-pick-go" href={tourHref(p)}>
                  Walk it first
                </a>
              ) : (
                <a className="ob-pick-go" href={`/map?place=${encodeURIComponent(p.property_id)}`}>
                  See on the map
                </a>
              )}
            </li>
          ))}
        </ol>
      )}
      {load.s === "ready" && (
        <p className="ob-fine">
          {load.asOf}. Researched, not a promise it is offered at this price.{" "}
          <a href="/listings">See all in Listings</a>
        </p>
      )}
    </article>
  );
}

function PicksCard({ picks, source }: { picks: FinderPick[]; source: DataSource }) {
  const sample = source === "fixture";
  return (
    <article className="ob-card ob-places" data-testid="ob-finder-picks">
      <header className="ob-card-head">
        <p className="ob-card-kicker">Leading your list</p>
        <SourceChip source={source} />
      </header>
      <ol className="ob-picks">
        {picks.map((p) => (
          <li key={p.pid} className="ob-pick" data-testid="ob-pick">
            <span className="ob-rank mono">{p.rank}</span>
            <div className="ob-pick-body">
              <p className="ob-pick-line">{p.line}</p>
              <p className="ob-muted">{p.why}</p>
              <span className="ob-stamp" data-by={p.chosen_by}>
                {STAMP[p.chosen_by]}
                {sample ? " · Sample place by the team" : ""}
              </span>
            </div>
            {sample ? (
              <a className="ob-pick-go" href="/listings" title="A sample place made by the team">
                Browse similar
              </a>
            ) : p.has_scan ? (
              <a className="ob-pick-go" href={`/tour/${encodeURIComponent(p.pid)}`}>
                Walk it first
              </a>
            ) : (
              <a className="ob-pick-go" href={`/map?place=${encodeURIComponent(p.pid)}`}>
                See on the map
              </a>
            )}
          </li>
        ))}
      </ol>
      <p className="ob-fine">
        Code filters and orders every place. The Finder picks which lead and says why.
      </p>
    </article>
  );
}

function OfferCard({
  proposal,
  onDecided,
}: {
  proposal: FinderProposal;
  onDecided: (p: FinderProposal, yes: boolean) => Promise<void>;
}) {
  const [done, setDone] = useState<null | boolean>(null);
  const [busy, setBusy] = useState(false);
  const answer = async (yes: boolean) => {
    setBusy(true);
    await onDecided(proposal, yes);
    setBusy(false);
    setDone(yes);
  };
  return (
    <article className="ob-card ob-offer" data-testid="ob-offer">
      <header className="ob-card-head">
        <p className="ob-card-kicker">Keep this?</p>
        <span className="ob-stamp" data-by={proposal.chosen_by}>
          {STAMP[proposal.chosen_by]}
        </span>
      </header>
      <p className="ob-card-text">{proposal.text}</p>
      <p className="ob-muted">Because {proposal.evidence}.</p>
      {done === null ? (
        <div className="ob-acts">
          <button
            type="button"
            className="ob-primary"
            disabled={busy}
            onClick={() => void answer(true)}
          >
            Yes, keep it
          </button>
          <button
            type="button"
            className="ob-secondary"
            disabled={busy}
            onClick={() => void answer(false)}
          >
            Not now
          </button>
        </div>
      ) : (
        <p className="ob-muted">{done ? "Kept." : "Not kept."}</p>
      )}
    </article>
  );
}

import { useCallback, useEffect, useId, useReducer, useRef, useState } from "react";

import { apiBase, apiFetchRead, fetchCard } from "../api";
import { answerAbout, isAgainst, type CaseAnswer } from "./caseAnswer";
import { headlineOf, toneWord } from "../cardStrings";
import cardHold from "../../../../fixtures/contracts/card_hold.json";
import sampleLivingRoom from "../assets/sample-living-room.webp";
import sampleLounge from "../assets/sample-lounge.webp";
import { SourceChip } from "../components/SourceChip";
import { RealtorQuote } from "../landing/RealtorQuote";
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
import { HomeTeam } from "../proofroom/HomeTeam";
import { PhotoPin, State, type StateKind } from "../ui";
import { Tag } from "../ui/Tag";
import { Elevation } from "./Elevation";
import {
  MODE,
  approveChallenge as defaultApprove,
  createCase as defaultCreateCase,
  fetchApiSource,
  type ApproveChallenge,
  type CreateCase,
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
  saferWords,
  SWITCH_LABEL,
  switchOf,
  VIEW_HREF,
  VIEW_NAME,
  withoutFacebookLinks,
  type CaseTopic,
  type Intent,
  type View,
} from "./intent";
import "./onebox.css";

/** Tap one to start. Both are about checking an ad: that is the product. Each goes through the
 * same routing as typed words. */
export const EXAMPLES = ["Paste the ad you were sent", "Is this landlord real?"] as const;

/** How it works, in three lines (focus plan section 1). The same words as the README. */
export const HOW = [
  {
    title: "Send the ad",
    text: "Text it to SNAPBACK on iMessage, or paste it in the one box: words, screenshots, or both.",
  },
  {
    title: "We check it",
    text: "Scam-pattern rules run on any ad; CoStar's record of the building adds rent, leasing office, manager and website; where CoStar has a 3D scan, we place the ad's photos in it.",
  },
  {
    title: "You get a report",
    text: "A verdict in plain words, the ad beside the real listing, what to do next, and safer homes on Apartments.com.",
  },
] as const;

/** The card's two rules, as the answer to any question about paying. Written by code. */
export const RULES_REPLY =
  "Two rules: never pay before a signed lease and a viewing, and never pay by Zelle, wire or gift card. If you have the ad, paste it here and I'll check it.";

export const FB_ASK =
  "Facebook keeps listings behind a login. Paste the listing text here and add its photos, and I'll check it.";

/** The one measured line on Home (A8, n stated). Locked text: never add to it. */
export const MEASURED =
  "Measured on 78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it";

/** What the button says: it follows the same routing as the message will. */
export function sendLabel(text: string, files: number, caseOnScreen: boolean): string {
  if (!text.trim() && files === 0) return "Check it";
  const kind = route({ text, files, caseOnScreen }).kind;
  if (kind === "find") return "Find places";
  return kind === "check" || kind === "check-ask" || kind === "check-fb" ? "Check it" : "Ask";
}

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

export type Item =
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
  | { id: number; type: "offer"; proposal: FinderProposal; source: DataSource }
  | { id: number; type: "answer"; answer: CaseAnswer }
  | { id: number; type: "open"; view: View }
  | { id: number; type: "error"; text: string };

type ItemInput = Item extends infer T ? (T extends Item ? Omit<T, "id"> : never) : never;

interface Props {
  createCase?: CreateCase;
  approveChallenge?: ApproveChallenge;
  checkingMs?: number;
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
  const root = useRef<HTMLDivElement>(null);
  const dock = useRef<HTMLDivElement>(null);
  // The card of each finished case and the ad's own words, kept so a follow-up is answered from
  // them. A tick makes the thread scroll again when a card lands after its row was added.
  const cardsRef = useRef<Record<string, Card>>({});
  const adRef = useRef<Record<string, string>>({});
  const [landed, setLanded] = useState(0);
  // Checks that ended without a card (the server refused, or the card never came).
  const [checksFailed, setChecksFailed] = useState(0);

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

  // The docked box covers the bottom of the page. The thread keeps that much room under its last
  // row (--ob-dock-h, measured), so the last action row can always scroll fully above the box.
  const docked = items.length > 0;
  useEffect(() => {
    const el = dock.current;
    const host = root.current;
    if (!el || !host) return;
    // The box is pinned a little above the bottom edge on a phone (the tab bar sits under it),
    // so what it covers is its height plus that offset.
    const measure = () => {
      const lift = Number.parseFloat(getComputedStyle(el).bottom) || 0;
      host.style.setProperty(
        "--ob-dock-h",
        `${Math.ceil(el.getBoundingClientRect().height + lift)}px`,
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, [docked]);

  useEffect(() => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    end.current?.scrollIntoView?.({ behavior: still ? "auto" : "smooth", block: "end" });
  }, [items.length, busy, landed]);

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
    async (raw: string, asWish: boolean) => {
      // A Facebook address is never sent to the Finder: only the renter's own words go.
      const words = withoutFacebookLinks(raw);
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
          ...offers
            .slice(0, 1)
            .map((proposal) => ({ type: "offer" as const, proposal, source: reply.source })),
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

  /** A follow-up about the case on screen, answered from its card and never by the Finder. */
  const answerCase = useCallback(
    async (topic: CaseTopic) => {
      const id = cases[cases.length - 1];
      if (!id) {
        add({ type: "bot", by: "policy", text: "Paste an ad first, and I'll answer about it." });
        return;
      }
      let card = cardsRef.current[id];
      if (!card) {
        setBusy("Reading the result");
        try {
          card = await fetchCard(id);
          cardsRef.current[id] = card;
        } catch (err) {
          add({
            type: "error",
            text: err instanceof Error ? err.message : "The result did not load.",
          });
          return;
        } finally {
          setBusy(null);
        }
      }
      add({ type: "answer", answer: answerAbout(card, topic) });
    },
    [add, cases],
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
      if (intent.kind === "rules") {
        add({ type: "bot", by: "policy", text: RULES_REPLY });
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
        void answerCase(intent.topic);
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
    [add, answerCase, findWith, knownRent],
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

  // The rail beside the thread: the newest case, and whether its card is still on the way.
  const lastCase = cases[cases.length - 1];
  const railCard = lastCase ? (cardsRef.current[lastCase] ?? null) : null;
  const checksAsked = items.filter((it) => it.type === "check").length;
  const checking = checksAsked > Object.keys(cardsRef.current).length + checksFailed;

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
      label={sendLabel(text, files.length, cases.length > 0)}
    />
  );

  return (
    <div className="ob" ref={root} data-empty={empty || undefined} data-testid="one-box">
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
      {!empty && <ThreadRail card={checking ? null : railCard} checking={checking} />}

      {empty ? (
        <section className="ob-start" aria-labelledby="ob-title">
          <div className="ob-hero">
            <div className="ob-field" aria-hidden="true" />
            <div className="ob-hero-in">
              <h1 id="ob-title" className="ob-title">
                <span>Send a rental ad before you pay.</span>{" "}
                <span className="ob-title-ask">
                  Get a report: is this the real listing, and who do you call?
                </span>
              </h1>
              <aside className="ob-side" aria-label="How it works">
                <Elevation />
                <p className="ob-side-note ui-mono">A drawing, not a photo. No real address.</p>
                <ol className="ob-how" aria-label="How it works" data-testid="ob-how">
                  {HOW.map((step, i) => (
                    <li key={step.title}>
                      <span className="ob-how-n ui-mono">{`0${i + 1}`}</span>
                      <b>{step.title}</b>
                      <span className="ob-how-text">{step.text}</span>
                    </li>
                  ))}
                </ol>
              </aside>
              <div className="ob-ask">
                {composer}
                {(error || fileErrors.length > 0) && (
                  <Problems error={error} fileErrors={fileErrors} />
                )}
                <ul className="ob-examples" aria-label="Try one">
                  {EXAMPLES.map((ex) => (
                    <li key={ex}>
                      <button type="button" className="ob-example" onClick={() => submit(ex, [])}>
                        {ex}
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="ob-measured-row">
                  <p className="ob-measured ui-mono" data-testid="ob-measured">
                    {MEASURED}
                  </p>
                  <Tag source="live" />
                </div>
              </div>
            </div>
          </div>
          <div className="ob-below">
            <div className="ob-cols">
              <WaysIn />
              <SampleCase onOpen={() => submit(SAMPLE_AD, [])} />
            </div>
            <div className="ob-cols ob-cols-even">
              <YourChecks />
              <RealtorQuote />
            </div>
            <footer className="ob-foot">
              <p className="ob-honest">
                <SourceChip source={shownMode} />
                <span>
                  SNAPBACK never messages anyone for you and never asks for money. Code sets every
                  verdict. A model, the Planner, picks up to 2 extra checks for what the card could
                  not confirm and drafts a next step it never sends. It never sets the verdict.
                </span>
              </p>
              <p className="ob-credits">
                Sample photos by {PHOTO_CREDITS} on Unsplash. They are not the homes we check.
              </p>
            </footer>
          </div>
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
                onCase={(id, ad) => {
                  adRef.current[id] = ad;
                  setCases((c) => (c.includes(id) ? c : [...c, id]));
                }}
                onFail={() => setChecksFailed((n) => n + 1)}
                onCard={(card) => {
                  cardsRef.current[card.case_id] = card;
                  setLanded((n) => n + 1);
                }}
                onFollow={(words) => {
                  const last = cases[cases.length - 1];
                  submit(
                    words === SAFER_LABEL ? saferWords(adRef.current[last ?? ""] ?? "") : words,
                    [],
                  );
                }}
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
            {!busy && !checking && (
              <NextMoves hasCase={railCard !== null} onAsk={(words) => submit(words, [])} />
            )}
          </ol>
          <div ref={end} />
          <div className="ob-dock" ref={dock}>
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

const SAMPLE_CARD = cardHold as Card;

const PHOTO_CREDITS = [
  "Minh Pham",
  "Collov Home Design",
  "Raphael (Ajani Kamali Akio)",
  "Tobias Wilden",
  "Marlene Céline Nordvik",
].join(", ");

// The sample case that hangs off the bottom edge of the hero. It shows proof, not a feature
// list: the ad's photo beside the same view found in the building's 3D scan, then the line that
// placed it and the line that most needs attention. Verdict and lines are the team's own fixture
// card (the code's words); the pictures are one stock interior, stamped as a sample on both
// sides. One tap runs the sample ad through the box.
function SampleCase({ onOpen }: { onOpen: () => void }) {
  const card = SAMPLE_CARD;
  const all = card.rows.flatMap((row) => row.lines.map((line) => ({ kind: row.kind, line })));
  const order = (t: string) => ({ red_flag: 0, hold: 1, not_shown: 1, ok: 2 })[t] ?? 3;
  const placed = all.find((l) => l.kind === "place");
  const flagged = [...all]
    .filter((l) => l !== placed)
    .sort((a, b) => order(a.line.tone) - order(b.line.tone))[0];
  const lines = [placed, flagged].filter((l) => l !== undefined);
  return (
    <button type="button" className="ob-sample ui-sheet" data-testid="ob-sample" onClick={onOpen}>
      <span className="ob-sample-head ui-mono">
        <span>Sample report {card.case_id}</span>
        <SourceChip source="fixture" />
      </span>
      <span className="ob-pair" data-testid="ob-pair">
        {(
          [
            ["The ad's photo", sampleLounge, "a living room with a pale green sofa"],
            [
              "Found in the building's 3D scan",
              sampleLivingRoom,
              "a living room with a grey sofa and plants, standing in for the scan view",
            ],
          ] as const
        ).map(([label, src, what]) => (
          <span key={label} className="ob-pair-side">
            <SamplePhoto src={src} alt={`${label}: ${what}`}>
              <PhotoPin n={1} x={38} y={56} />
              <PhotoPin n={2} x={66} y={34} />
            </SamplePhoto>
            <span className="ob-pair-label ui-mono">{label}</span>
          </span>
        ))}
      </span>
      <span className="ob-sample-verdict" data-tone={TONE_OF[card.state]}>
        {headlineOf(card)}
      </span>
      <span className="ob-sample-rows">
        {lines.map(({ kind, line }) => {
          const word = toneWord(line.tone, kind);
          return (
            <span key={`${kind}-${line.label}`} className="ob-sample-row">
              <span className="ob-sample-what">
                <span className="ob-sample-text">{line.text}</span>
              </span>
              <State kind={(WORD_TONE[word] ?? "unchecked") as StateKind}>{word}</State>
            </span>
          );
        })}
      </span>
      <span className="ob-sample-go">
        <span>Open the sample report</span>
        <span aria-hidden="true">→</span>
      </span>
    </button>
  );
}

/** Where the app opens up from the box. Two lead rows (the map, the Finder), then the rest. */
export const WAYS = [
  {
    href: "/map",
    title: "The map",
    text: "Every researched place, by where it is. Tap one to see what the record says.",
    lead: true,
  },
  {
    href: "/finder",
    title: "The Finder",
    text: "Say what you need. It ranks places, shows why, and keeps only what you say yes to.",
    lead: true,
  },
  {
    href: "/listings",
    title: "Listings and tour prep",
    text: "Browse the researched places and get ready to visit one.",
    lead: false,
  },
  {
    href: "/stories",
    title: "All stories",
    text: "Imagined renters, played out step by step.",
    lead: false,
  },
  {
    href: "/reviews",
    title: "Reviews and reports",
    text: "What people who tried SNAPBACK said, counted.",
    lead: false,
  },
] as const;

/** The arrow at the end of a row: drawn, one stroke, the same everywhere. */
function GoArrow() {
  return (
    <svg className="ob-way-go" viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
      <path d="M3.5 10h12M11 5.5l4.5 4.5-4.5 4.5" />
    </svg>
  );
}

// The ways in, as an index of rows on hairlines: no tiles. Checking an ad stays the one filled
// action on the page; these are ink links. Your recent checks sit in their own block below.
function WaysIn() {
  return (
    <nav className="ob-ways" aria-labelledby="ob-ways-title" data-testid="ob-ways">
      <header className="yc-head">
        <h2 id="ob-ways-title" className="yc-title">
          Or start somewhere else
        </h2>
      </header>
      <ul className="ob-ways-list">
        {WAYS.map((w) => (
          <li key={w.href} data-lead={w.lead || undefined}>
            {/* Stories keeps the short name other pages and tests know it by. */}
            <a
              className="ob-way"
              href={w.href}
              aria-label={w.href === "/stories" ? w.title : undefined}
            >
              <span className="ob-way-main">
                <span className="ob-way-title">{w.title}</span>
                <span className="ob-way-text">{w.text}</span>
              </span>
              <GoArrow />
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The three things a check looks at, numbered as on the drawing. */
export const RAIL = [
  { kind: "place", n: "01", name: "Place", ask: "Is the home where the ad says it is?" },
  { kind: "person", n: "02", name: "Person", ask: "Who posted it, against the office on record." },
  { kind: "price", n: "03", name: "Price", ask: "The rent, against the building's record." },
] as const;

// Beside the thread on a wide screen: the drawing stays, and under it the three checks. Before
// a check they say what will be looked at; during one they tick; after it each carries the
// state word of its most serious line on the card (the card's own words, set by code).
function ThreadRail({ card, checking }: { card: Card | null; checking: boolean }) {
  const order = (t: string) => ({ red_flag: 0, hold: 1, not_shown: 1, ok: 2 })[t] ?? 3;
  return (
    <aside className="ob-rail" aria-label="What is being checked" data-testid="ob-rail">
      <Elevation />
      <p className="ob-side-note ui-mono">A drawing, not a photo. No real address.</p>
      <h2 className="ob-rail-title ui-mono">
        {card
          ? `Case ${card.case_id}: what the check found`
          : checking
            ? "Checking now"
            : "What a check looks at"}
      </h2>
      <ol className="ob-rail-rows" data-checking={checking || undefined}>
        {RAIL.map((r) => {
          const row = card?.rows.find((x) => x.kind === r.kind);
          const worst = row && [...row.lines].sort((a, b) => order(a.tone) - order(b.tone))[0];
          const word = worst ? toneWord(worst.tone, r.kind) : null;
          return (
            <li key={r.kind}>
              <span className="ob-rail-n ui-mono">{r.n}</span>
              <span className="ob-rail-main">
                <b>{r.name}</b>
                <span className="ob-rail-ask">{r.ask}</span>
              </span>
              {word ? (
                <span className="ob-rail-state">
                  <State kind={(WORD_TONE[word] ?? "unchecked") as StateKind}>{word}</State>
                </span>
              ) : checking ? (
                <span className="ob-rail-wait ui-mono">Checking</span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

// What to do next, as rows under the last answer: two things to ask, then the map and the
// Finder. Asking goes through the box's own routing, exactly as typed words would.
function NextMoves({ hasCase, onAsk }: { hasCase: boolean; onAsk: (words: string) => void }) {
  const asks = hasCase
    ? [
        { say: NEXT_REAL, title: NEXT_REAL, text: "The short answer, from the checks above." },
        { say: WHO_LABEL, title: WHO_LABEL, text: "The office on record, and where to report it." },
      ]
    : [
        {
          say: SAMPLE_AD,
          title: "Try the sample ad",
          text: "A made-up ad with the red flags a real one carries. See the full report.",
        },
      ];
  const links = WAYS.filter((w) => w.lead);
  return (
    <li className="ob-next" data-testid="ob-next">
      <span className="ob-next-title ui-mono">Next</span>
      <ul className="ob-next-list">
        {asks.map((a) => (
          <li key={a.title}>
            <button type="button" className="ob-way ob-next-row" onClick={() => onAsk(a.say)}>
              <span className="ob-way-main">
                <span className="ob-way-title">{a.title}</span>
                <span className="ob-way-text">{a.text}</span>
              </span>
              <GoArrow />
            </button>
          </li>
        ))}
        {links.map((w) => (
          <li key={w.href}>
            <a className="ob-way ob-next-row" href={w.href}>
              <span className="ob-way-main">
                <span className="ob-way-title">{w.title}</span>
                <span className="ob-way-text">{w.text}</span>
              </span>
              <GoArrow />
            </a>
          </li>
        ))}
      </ul>
    </li>
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

/** A licensed stock photo, always stamped as a sample so nobody takes it for the place. */
export function SamplePhoto({
  src,
  alt,
  children,
}: {
  src: string;
  alt: string;
  children?: React.ReactNode;
}) {
  return (
    <span className="ob-photo" data-testid="sample-photo">
      <img src={src} alt={alt} loading="lazy" />
      {children}
      <span className="ob-photo-stamp">Sample photo</span>
    </span>
  );
}

/**
 * The scan view this case's photo matched, read at run time from the API with the case's read
 * token. Never bundled: kit pictures stay on the server. Null until it loads, or when there is
 * none (fixture mode, no token, no placed photo).
 */
function useScanPhoto(caseId: string, lookup: boolean): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    // An ad with no photos has no evidence file; asking for it would only log a 404.
    if (!apiBase() || !lookup) return;
    const ctrl = new AbortController();
    let made: string | null = null;
    (async () => {
      try {
        const ev = await apiFetchRead(`/cases/${encodeURIComponent(caseId)}/evidence`, caseId, {
          signal: ctrl.signal,
        });
        if (!ev?.ok) return;
        const body = (await ev.json()) as { photos?: { alias: string; status: string }[] };
        // Only a photo placed in the claimed home: another home's scan would mislead.
        const photo = body.photos?.find((p) => p.status === "located_in_claimed") ?? null;
        if (!photo) return;
        const img = await apiFetchRead(
          `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(photo.alias)}/scan.jpg`,
          caseId,
          { signal: ctrl.signal },
        );
        if (!img?.ok) return;
        made = URL.createObjectURL(await img.blob());
        if (!ctrl.signal.aborted) setUrl(made);
      } catch {
        // No picture: the sample photo stays, stamped as one.
      }
    })();
    return () => {
      ctrl.abort();
      if (made) URL.revokeObjectURL?.(made);
    };
  }, [caseId, lookup]);
  return url;
}

/** The "Walk it first" card under a verdict: the real scan view when the API has one. */
function WalkCard({ caseId, lookup }: { caseId: string; lookup: boolean }) {
  const scan = useScanPhoto(caseId, lookup);
  const id = encodeURIComponent(caseId);
  return (
    <a className="ob-walk" href={`/case/${id}/twin`} data-testid="ob-walk">
      {scan ? (
        <span className="ob-photo">
          <img src={scan} alt="The scan view this ad's photo matched" />
          <span className="ob-photo-stamp">From the 3D scan</span>
        </span>
      ) : (
        <SamplePhoto src={sampleLivingRoom} alt="A living room with a grey sofa and plants" />
      )}
      <span className="ob-walk-text">
        <span className="ob-walk-name">Walk it first</span>
        <span className="ob-can-line">See the place room by room before you go or pay.</span>
      </span>
    </a>
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

export function Composer({
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
  label,
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
  label: string;
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
              ? "Paste the ad you were sent, or its link. Or ask: is this landlord real?"
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
          aria-label="Add screenshots"
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
          <span>{label}</span>
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------------------------
// The thread.

export function ThreadItem({
  it,
  mode,
  props,
  onSwitch,
  onReply,
  onCase,
  onCard,
  onFail,
  onFollow,
  onDecided,
}: {
  it: Item;
  mode: DataSource;
  props: Props;
  onSwitch: (to: Intent) => void;
  onReply: (reply: string, kind: "rent" | "send" | "unsure") => void;
  onCase: (id: string, adText: string) => void;
  onCard?: (card: Card) => void;
  onFail?: () => void;
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
            onCard={onCard}
            onFail={onFail}
            onFollow={onFollow}
          />
        </li>
      );
    case "answer":
      return <AnswerItem answer={it.answer} />;
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
          <OfferCard proposal={it.proposal} source={it.source} onDecided={onDecided} />
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

/** The label of the verdict's button for safer homes; Home turns it into the ad's own filter. */
export const SAFER_LABEL = "Find safer homes";
const WHO_LABEL = "Who do I call?";
export const NEXT_REAL = "Is this a real listing?";

/** A reply about the case on screen: the card's own lines, with a short lead-in from code. */
function AnswerItem({ answer }: { answer: CaseAnswer }) {
  return (
    <li className="ob-bot ob-answer" data-testid="ob-answer">
      <p className="ob-answer-lead">{answer.lead}</p>
      {answer.sections.map((sec, i) => (
        <div key={i} className="ob-answer-sec">
          {sec.heading && <p className="ob-answer-head">{sec.heading}</p>}
          <ul>
            {sec.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ))}
      <p className="ob-answer-links">
        {answer.links.map((l) => (
          <a
            key={l.href}
            href={l.href}
            {...(l.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
          >
            {l.label}
            {l.external ? <span aria-hidden="true"> ↗</span> : null}
          </a>
        ))}
      </p>
      <span className="ob-stamp" data-by="policy">
        Written by code from this result
      </span>
    </li>
  );
}

// --- The ad check, inline. The verdict comes first; asking the poster for proof comes after it.

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
  onCard,
  onFail,
  onFollow,
}: {
  input: { link: string | null; text: string | null; files: File[] };
  mode: DataSource;
  props: Props;
  onCase: (id: string, adText: string) => void;
  onCard?: (card: Card) => void;
  onFail?: () => void;
  onFollow: (words: string) => void;
}) {
  const {
    createCase = defaultCreateCase,
    approveChallenge = defaultApprove,
    checkingMs = 900,
  } = props;
  const [state, dispatch] = useReducer(reduce, initialState);
  const started = useRef(false);
  const deciding = useRef(false);
  // The drafted message, kept for after the verdict (the reducer drops it once the result is in).
  const [challenge, setChallenge] = useState<string | null>(null);
  // Tell Home once if this check ends in an error, so the rail stops saying "Checking".
  const failTold = useRef(onFail);
  useEffect(() => {
    failTold.current = onFail;
  });
  const failed = state.step === "error";
  useEffect(() => {
    if (failed) failTold.current?.();
  }, [failed]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    dispatch({ type: "submit" });
    createCase(input)
      .then((made) => {
        setChallenge(made.challenge_text);
        dispatch({
          type: "created",
          caseId: made.case_id,
          challengeText: made.challenge_text,
          source: made.source,
        });
      })
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

  // Verdict first: the check does not stop to ask. Nothing is ever sent for the renter, so the
  // answer to the poster is recorded as "not now" and the result shows at once. The drafted
  // message is offered under the verdict, to copy and send yourself.
  const approvalCase = state.step === "approval" ? state.caseId : null;
  useEffect(() => {
    if (approvalCase === null || deciding.current) return;
    deciding.current = true;
    void (async () => {
      if (mode === "live") {
        try {
          await approveChallenge(approvalCase, "cancel");
        } catch (err) {
          deciding.current = false;
          dispatch({
            type: "fail",
            message: err instanceof Error ? err.message : "Something went wrong. Try again.",
          });
          return;
        }
      }
      deciding.current = false;
      dispatch({ type: "skip" });
    })();
  }, [approvalCase, mode, approveChallenge]);

  const doneCase = state.step === "done" ? state.caseId : null;
  const adText = input.text ?? "";
  useEffect(() => {
    if (doneCase) onCase(doneCase, adText);
  }, [doneCase, adText, onCase]);

  if (state.step === "done")
    return (
      <VerdictCard
        caseId={state.caseId}
        source={state.source}
        onFollow={onFollow}
        onCard={onCard}
        challenge={challenge}
        scanLookup={input.files.length > 0 || input.link !== null}
      />
    );

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

  // The approval step passes at once; it shows as the check still running. The check team
  // stands in for the old progress steps: every member waits until the case exists, then the
  // lights are the case's own recorded steps.
  const source: DataSource = "source" in state ? state.source : mode;
  return (
    <article className="ob-card ob-check" data-testid="ob-check">
      <header className="ob-card-head">
        <p className="ob-card-kicker">Checking the ad</p>
        <SourceChip source={source} />
      </header>
      <HomeTeam caseId={"caseId" in state ? state.caseId : null} />
    </article>
  );
}

/** The check's four steps, the one at `active` lit. */
export function CheckSteps({
  active,
  steps = STEPS,
}: {
  active: number;
  steps?: readonly { key: string; label: string }[];
}) {
  return (
    <ol className="ob-steps" aria-label="Progress">
      {steps.map((s, i) => {
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
  );
}

/** The photo challenge, drafted for the renter to send themselves. Nothing is sent for them. */
export function ChallengeDraft({
  text,
  busy,
  copied,
  onSend,
  onCopy,
  onSkip,
}: {
  text: string;
  busy: boolean;
  copied: boolean;
  onSend: () => void;
  onCopy: () => void;
  onSkip: () => void;
}) {
  return (
    <section className="ob-approve" aria-labelledby="ob-approve-title">
      <h2 id="ob-approve-title" className="ob-card-title">
        Ask the poster for proof
      </h2>
      <p className="ob-card-text">
        A real landlord can send a fresh photo from inside the unit. Copy this and send it yourself.
        Nothing is sent for you.
      </p>
      <label htmlFor="challenge" className="sr-only">
        Message to send
      </label>
      <textarea
        id="challenge"
        className="ob-message"
        rows={4}
        readOnly
        value={text}
        onFocus={(e) => e.currentTarget.select()}
      />
      <div className="ob-acts">
        <button type="button" className="ob-primary" disabled={busy} onClick={onSend}>
          I approve it and I will send it
        </button>
        <button type="button" className="ob-secondary" onClick={onCopy}>
          {copied ? "Copied" : "Copy message"}
        </button>
        <button type="button" className="ob-quiet" disabled={busy} onClick={onSkip}>
          Skip this, show the result
        </button>
      </div>
    </section>
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
  onCard,
  challenge = null,
  scanLookup = true,
}: {
  caseId: string;
  source: DataSource;
  onFollow?: (words: string) => void;
  /** Told once when the card has loaded, so Home can answer follow-ups from it. */
  onCard?: (card: Card) => void;
  /** The message drafted for the poster, offered after the verdict. */
  challenge?: string | null;
  /** False when the ad had no photos, so the API has no scan view to ask for. */
  scanLookup?: boolean;
}) {
  const [card, setCard] = useState<Card | null | "error">(null);
  const told = useRef(onCard);
  useEffect(() => {
    told.current = onCard;
  });
  useEffect(() => {
    const ctrl = new AbortController();
    fetchCard(caseId, ctrl.signal)
      .then((c) => {
        setCard(c);
        told.current?.(c);
      })
      .catch(() => !ctrl.signal.aborted && setCard("error"));
    return () => ctrl.abort();
  }, [caseId]);
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
  return (
    <VerdictView
      card={card}
      source={source}
      onFollow={onFollow}
      challenge={challenge}
      scanLookup={scanLookup}
      team={<HomeTeam caseId={caseId} />}
    />
  );
}

/** The verdict card itself, from a Card already in hand. `actions` replaces the two links (the
 *  Stories page shows them as they look, without leaving the story). */
export function VerdictView({
  card,
  source,
  onFollow,
  actions,
  team,
  challenge = null,
  scanLookup = true,
}: {
  card: Card;
  source: DataSource;
  onFollow?: (words: string) => void;
  actions?: React.ReactNode;
  /** The check team's strip for this case, with "Watch them work". */
  team?: React.ReactNode;
  challenge?: string | null;
  scanLookup?: boolean;
}) {
  const [all, setAll] = useState(false);
  // A red flag or a hold keeps only the paths that help: the report, who to call, safer homes.
  const against = isAgainst(card);
  const id = encodeURIComponent(card.case_id);
  const allLines = card.rows.flatMap((row) =>
    row.lines.map((line, i) => ({ kind: row.kind, line, first: i === 0, key: `${row.kind}-${i}` })),
  );
  // Answer first: the lines that most need attention, then the rest one tap below.
  const order = (t: string) => ({ red_flag: 0, hold: 1, not_shown: 1, ok: 2 })[t] ?? 3;
  const ranked = [...allLines].sort((a, b) => order(a.line.tone) - order(b.line.tone));
  const firstLines = ranked.slice(0, FIRST_LINES);
  // Every part of the check shows at least once (place, person, price), so a quiet "Matches"
  // on the place is never hidden behind the warnings.
  for (const row of card.rows) {
    const one = ranked.find((l) => l.kind === row.kind);
    if (one && !firstLines.some((l) => l.kind === row.kind)) firstLines.push(one);
  }
  const shownLines = all
    ? allLines
    : firstLines.map((l, i, list) => ({ ...l, first: i === 0 || list[i - 1]!.kind !== l.kind }));
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
      <h2 className="ob-verdict-word">{headlineOf(card)}</h2>
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
      {allLines.length > firstLines.length && (
        <button type="button" className="ob-more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `How we know: all ${allLines.length} checks`}
        </button>
      )}
      <p className="ob-muted">Not checked: {card.not_checked.join(", ")}.</p>
      {team}
      <div className="ob-acts">
        {actions ?? (
          <>
            <a className="ob-primary" href={`/case/${id}`}>
              Open the full report
            </a>
            {!against && (
              <a className="ob-quiet" href={`/case/${id}/prep`}>
                Get ready to visit
              </a>
            )}
          </>
        )}
      </div>
      {!actions && !against && <WalkCard caseId={card.case_id} lookup={scanLookup} />}
      {onFollow && (
        <ul className="ob-replies ob-follow" aria-label="Next">
          {(against
            ? [WHO_LABEL, SAFER_LABEL]
            : [SAFER_LABEL, "Show me on the map", "Replay a real case"]
          ).map((w) => (
            <li key={w}>
              <button type="button" onClick={() => onFollow(w)}>
                {w}
              </button>
            </li>
          ))}
        </ul>
      )}
      {challenge && !actions && <ProofAsk text={challenge} />}
    </article>
  );
}

/** After the verdict: the message that asks the poster for a fresh photo, to copy and send
 *  yourself. A second step, never a gate in front of the result. */
function ProofAsk({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const fieldId = useId();
  const draft = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) draft.current?.scrollIntoView?.({ block: "nearest" });
  }, [open]);
  return (
    <section className="ob-proof-ask" aria-label="Ask the poster for proof">
      <button
        type="button"
        className="ob-secondary"
        aria-expanded={open}
        data-testid="ob-proof-toggle"
        onClick={() => setOpen(!open)}
      >
        Ask the poster for proof
      </button>
      {open && (
        <div
          className="ob-approve"
          ref={draft}
          style={{ scrollMarginBottom: "calc(var(--ob-dock-h, 0px) + 12px)" }}
        >
          <p className="ob-card-text">
            A real landlord can send a fresh photo from inside the unit. Copy this and send it
            yourself. Nothing is sent for you.
          </p>
          <label htmlFor={fieldId} className="sr-only">
            Message to send
          </label>
          <textarea
            id={fieldId}
            className="ob-message"
            rows={4}
            readOnly
            value={text}
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="ob-acts">
            <button
              type="button"
              className="ob-secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(text);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
            >
              {copied ? "Copied" : "Copy message"}
            </button>
          </div>
        </div>
      )}
    </section>
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
        {/* Until the server says what it served, claim only FIXTURE, never LIVE. */}
        <SourceChip source={load.s === "ready" ? load.source : "fixture"} />
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

export function PicksCard({
  picks,
  source,
  act,
}: {
  picks: FinderPick[];
  source: DataSource;
  /** Replaces each pick's one next step (the Stories page shows "Walk it first" on a sample). */
  act?: (p: FinderPick) => React.ReactNode;
}) {
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
            {act ? (
              act(p)
            ) : sample ? (
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

export function OfferCard({
  proposal,
  source,
  onDecided,
}: {
  proposal: FinderProposal;
  source: DataSource;
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
        <span className="ob-card-tags">
          <span className="ob-stamp" data-by={proposal.chosen_by}>
            {STAMP[proposal.chosen_by]}
          </span>
          <SourceChip source={source} />
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

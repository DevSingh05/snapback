import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { SourceChip } from "../components/SourceChip";
import type { TraceEvent } from "../contracts";
import { ChallengeDraft, CheckSteps, Composer, ThreadItem } from "../home/OneBox";
import { TourDraftView } from "../search/PlacesStrip";
import { TraceLine } from "../trace";
import { frameClock, WalkPlayer, type Clock } from "../walk/player";
import type { Ad, WalkSet } from "./data";
import { useCount, useTyped } from "./player";
import { withId, you, routed, type ThreadEntry } from "./thread";

// The pieces a story beat is made of. Each one is the app's own component with sample data, laid
// out as it is in the app, so what plays here is what a renter sees.

export interface SceneCtx {
  playing: boolean;
  reduced: boolean;
  ms: number;
}

const noop = () => undefined;
const asyncNoop = async () => undefined;

/** A real photo standing in for a listing photo: always says so. */
export function Stamp({ children = "Sample photo" }: { children?: ReactNode }) {
  return <span className="st-stamp mono">{children}</span>;
}

// --- The ad, as the renter saw it. A plain listing layout, no platform's branding. -----------------

export function AdScene({ ad }: { ad: Ad }) {
  return (
    <article className="st-ad" data-testid="st-ad" aria-label={`The ad: ${ad.title}`}>
      <figure className="st-ad-photo">
        <img src={ad.photo} alt={ad.photoAlt} />
        <Stamp />
        <span className="st-ad-count mono">1 / {ad.photos}</span>
      </figure>
      <div className="st-ad-body">
        <p className="st-ad-where mono">{ad.where}</p>
        <p className="st-ad-price">{ad.price}</p>
        <h3 className="st-ad-title">{ad.title}</h3>
        <p className="st-ad-place">{ad.place}</p>
        <p className="st-ad-text">{ad.body}</p>
        <p className="st-ad-note">Ad written by the team for this story.</p>
      </div>
    </article>
  );
}

// --- The one box, with words going in. --------------------------------------------------------------

type FakeVoice = Parameters<typeof Composer>[0]["voice"];

function fakeVoice(over: Partial<FakeVoice>): FakeVoice {
  return {
    engine: "browser",
    state: "idle",
    level: 0,
    interim: "",
    error: null,
    note: null,
    start: noop,
    stop: noop,
    cancel: noop,
    ...over,
  } as FakeVoice;
}

function StoryComposer({
  text,
  files = [],
  voice,
}: {
  text: string;
  files?: string[];
  voice?: FakeVoice;
}) {
  const box = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [made] = useState(() => files.map((f) => new File([f], f, { type: "image/jpeg" })));
  return (
    <Composer
      text={text}
      setText={noop}
      files={made}
      setFiles={noop}
      take={noop}
      dragging={false}
      setDragging={noop}
      onSend={noop}
      busy={false}
      voice={voice ?? fakeVoice({})}
      fileInput={fileInput}
      box={box}
      big
    />
  );
}

export function TypeScene({
  words,
  files,
  ctx,
}: {
  words: string;
  files?: string[];
  ctx: SceneCtx;
}) {
  const typed = useTyped(words, ctx.playing, ctx.reduced, ctx.ms);
  return (
    <div className="ob st-ob" data-testid="st-type">
      <p className="st-app-title">Found a place online? Ask before you pay.</p>
      <StoryComposer text={typed} files={typed.length === words.length ? files : []} />
    </div>
  );
}

/** Talking to the box: the mic is held and the words come in as they are heard. */
export function VoiceScene({ heard, ctx }: { heard: string; ctx: SceneCtx }) {
  const typed = useTyped(heard, ctx.playing, ctx.reduced, ctx.ms);
  const [level, setLevel] = useState(0.5);
  useEffect(() => {
    if (!ctx.playing || ctx.reduced) return;
    const t = setInterval(() => setLevel(0.3 + Math.random() * 0.6), 140);
    return () => clearInterval(t);
  }, [ctx.playing, ctx.reduced]);
  return (
    <div className="ob st-ob" data-testid="st-voice">
      <p className="st-app-title">Found a place online? Ask before you pay.</p>
      <StoryComposer
        text=""
        files={["listing-1.jpg", "listing-2.jpg", "listing-3.jpg"]}
        voice={fakeVoice({ state: "recording", interim: typed || "…", level })}
      />
      <p className="st-voice-note">
        <span className="st-mic-dot" aria-hidden="true" />
        Hold the mic and talk. It works from any phone, in any time zone.
      </p>
    </div>
  );
}

// --- The thread: what you sent, what the box did with it, and the cards that came back. ----------

export function ThreadScene({
  entries,
  children,
  testId,
}: {
  entries: ThreadEntry[];
  children?: ReactNode;
  testId: string;
}) {
  const [items] = useState(() => entries.map(withId));
  const end = useRef<HTMLDivElement>(null);
  // Like the app: the newest message sits at the bottom of the view.
  useLayoutEffect(() => {
    const box = end.current?.closest(".st-app");
    if (box) box.scrollTop = box.scrollHeight;
  });
  return (
    <div className="ob st-ob" data-testid={testId}>
      <ol className="ob-thread" aria-label="Conversation">
        {items.map((it) => (
          <ThreadItem
            key={it.id}
            it={it}
            mode="fixture"
            props={{}}
            onSwitch={noop}
            onReply={noop}
            onCase={noop}
            onFollow={noop}
            onDecided={asyncNoop}
          />
        ))}
        {children}
      </ol>
      <div ref={end} />
    </div>
  );
}

/** The ad check at work: the app's four steps, and the agent's plan as it writes it. */
export function CheckCard({ events, ctx }: { events: TraceEvent[]; ctx: SceneCtx }) {
  const n = useCount(
    events.length,
    ctx.playing,
    ctx.reduced,
    Math.max(500, ctx.ms / (events.length + 1)),
  );
  const active = n >= events.length ? 2 : 1;
  return (
    <li className="ob-card-row">
      <article className="ob-card ob-check" data-testid="ob-check">
        <header className="ob-card-head">
          <p className="ob-card-kicker">Checking the ad</p>
          <SourceChip source="fixture" />
        </header>
        <CheckSteps active={active} />
        <section className="trace-panel st-trace" aria-label="Agent trace">
          <p className="trace-judge">
            The agent decides what to check next. The code decides what the card says.
          </p>
          <ol className="trace-list">
            {events.slice(0, n).map((e) => (
              <TraceLine key={e.seq} event={e} />
            ))}
          </ol>
        </section>
      </article>
    </li>
  );
}

export function ProofScene({ text, you: line }: { text: string; you: string }) {
  return (
    <ThreadScene entries={[]} testId="st-proof">
      <li className="ob-card-row">
        <article className="ob-card ob-check">
          <header className="ob-card-head">
            <p className="ob-card-kicker">Before any money moves</p>
            <SourceChip source="fixture" />
          </header>
          <ChallengeDraft
            text={text}
            busy={false}
            copied={false}
            onSend={noop}
            onCopy={noop}
            onSkip={noop}
          />
        </article>
      </li>
      <li className="ob-you" data-testid="ob-you">
        <p>{line}</p>
      </li>
    </ThreadScene>
  );
}

export function DraftScene({
  draft,
  lead,
}: {
  draft: Parameters<typeof TourDraftView>[0]["draft"];
  lead: string;
}) {
  return (
    <ThreadScene entries={[you(lead), routed("find")]} testId="st-draft">
      <li className="ob-card-row">
        <article className="ob-card st-draft">
          <header className="ob-card-head">
            <p className="ob-card-kicker">Tour request, drafted for you</p>
            <SourceChip source={draft.source} />
          </header>
          <TourDraftView draft={draft} id="st-draft-text" copied={false} onCopy={noop} />
        </article>
      </li>
    </ThreadScene>
  );
}

// --- The walk: the app's walk player over the home's views. -----------------------------------

/** The walk's clock runs only while the story plays, so a pause holds the walk too. */
function storyClock(playing: { current: boolean }): Clock {
  return {
    start(onFrame) {
      if (typeof requestAnimationFrame !== "function") return noop;
      return frameClock.start((dt) => {
        if (playing.current) onFrame(dt);
      });
    },
  };
}

export function WalkScene({ set, ctx }: { set: WalkSet; ctx: SceneCtx }) {
  const [index, setIndex] = useState(ctx.reduced || !ctx.playing ? set.still : 0);
  const playing = useRef(ctx.playing);
  useEffect(() => {
    playing.current = ctx.playing;
  }, [ctx.playing]);
  const [clock] = useState(() => storyClock(playing));
  const stop = set.stops[index]!;
  const view = set.views[stop.key] ?? set.views.arrive!;
  return (
    <div className="st-walk-wrap" data-testid="st-walk">
      <div className="tour-stage st-walk">
        <div className="sv" data-main="real">
          <div className="sv-pane" data-role="main">
            <img
              key={stop.key}
              className="sv-still-img st-walk-img"
              src={view.src}
              alt={view.alt}
            />
          </div>
        </div>
        <Stamp>Sample photo · the real scan plays here on a live check</Stamp>
        <WalkPlayer
          stops={set.stops}
          index={index}
          onIndex={setIndex}
          reduced={ctx.reduced}
          autoStart={ctx.playing && !ctx.reduced}
          clock={clock}
          photos={set.photos}
          verdict={set.verdict}
        />
      </div>
    </div>
  );
}

// --- The end: what SNAPBACK did that they'd otherwise do by hand. --------------------------------

export function EndScene({
  line,
  onAgain,
  next,
}: {
  line: string;
  onAgain: () => void;
  next: { label: string; onGo: () => void } | null;
}) {
  return (
    <div className="st-end" data-testid="st-end">
      <p className="st-end-kicker mono">What SNAPBACK did</p>
      <p className="st-end-line">{line}</p>
      <div className="st-end-acts">
        <a className="st-btn st-btn-primary" href="/">
          Check your own ad
        </a>
        {next && (
          <button type="button" className="st-btn" onClick={next.onGo}>
            Next: {next.label}
          </button>
        )}
        <button type="button" className="st-btn st-btn-quiet" onClick={onAgain}>
          Watch again
        </button>
      </div>
    </div>
  );
}

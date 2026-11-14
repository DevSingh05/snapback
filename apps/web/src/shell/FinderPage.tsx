import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

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
import {
  loadReadAloud,
  saveReadAloud,
  synthesize,
  usePlayer,
  useVoiceInput,
  voiceStatus,
  VoiceOff,
  type VoiceStatus,
} from "./voice";
import "./shell.css";
import "./finder.css";

const KIND_LABEL: Record<FinderEvent["kind"], string> = {
  opened: "You opened",
  passed: "You passed on",
  criteria: "You changed a filter",
  remembered: "Remembered",
  note: "You",
};

/** Tap one to send it: the three things renters say most. */
const EXAMPLES = [
  "Under $1,500, no walk-ups",
  "Near downtown with parking",
  "Pets OK, 2 beds",
] as const;

/** After this long the working line says a full run can take about half a minute. */
const SLOW_MS = 6000;
/** A press on the mic longer than this is push-to-talk: letting go sends. */
const HOLD_MS = 350;

type Conn =
  | { state: "connecting" }
  | { state: "offline"; why: "none" | "down" }
  | { state: "ready"; auth: FinderAuth; fs: FinderState };

// The Finder: the deep agent that learns what the renter wants and helps them find it. When the
// Finder service runs, every message and every pick or pass on the map goes to it; it replies,
// offers what to remember (nothing applies until Yes) and leads the list. The renter can type or
// talk, and hear replies, through ElevenLabs on our server. Without the service the page says so
// and falls back to code rules on this device. No reply is ever made up.
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
    <div className="view fd-view" data-testid="finder-page">
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
        <FinderHead>
          <p className="fd-status" data-testid="finder-connecting">
            Connecting to the Finder…
          </p>
        </FinderHead>
      ) : (
        <OfflineFinder why={conn.why} onRetry={() => setConn({ state: "connecting" })} />
      )}
    </div>
  );
}

function FinderHead({ children, actions }: { children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="fd-head">
      <h1 className="fd-title">Tell it what you want in a home</h1>
      {children}
      {actions && <div className="fd-head-acts">{actions}</div>}
    </header>
  );
}

// ---------------------------------------------------------------------------------------------
// Small pieces shared by both modes.

function Icon({ name }: { name: "mic" | "send" | "speaker" | "stop" | "talk" | "close" }) {
  const paths: Record<typeof name, ReactNode> = {
    mic: (
      <>
        <rect x="9" y="3" width="6" height="11" />
        <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
      </>
    ),
    send: <path d="M4 12h14M13 6l6 6-6 6" />,
    speaker: (
      <>
        <path d="M4 9h4l5-4v14l-5-4H4z" />
        <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" />
      </>
    ),
    stop: <rect x="7" y="7" width="10" height="10" />,
    talk: (
      <>
        <path d="M4 5h16v11H9l-5 4z" />
        <path d="M9 9.5v2.5M12 8v5.5M15 9.5v2.5" />
      </>
    ),
    close: <path d="M6 6l12 12M18 6L6 18" />,
  };
  return (
    <svg
      className="fd-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="square"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

/** Live input level as seven bars. Each bar leans on the level a little differently. */
function LevelMeter({ level }: { level: number }) {
  const shape = [0.45, 0.7, 0.9, 1, 0.85, 0.65, 0.4];
  return (
    <span className="fd-meter" aria-hidden="true" data-testid="voice-meter">
      {shape.map((s, i) => (
        <span
          key={i}
          style={{ transform: `scaleY(${Math.max(0.12, Math.min(1, level * s * 1.6))})` }}
        />
      ))}
    </span>
  );
}

type Voice = ReturnType<typeof useVoiceInput>;

/**
 * One mic, like a dictation key: hold it and talk, let go to send; or tap once to start and tap
 * again to send. Keyboard: Enter or Space toggles.
 */
function MicButton({
  voice,
  disabled,
  onOpen,
}: {
  voice: Voice;
  disabled: boolean;
  onOpen: () => void;
}) {
  const pressed = useRef<{ at: number; was: boolean } | null>(null);
  const on = voice.state === "recording";
  return (
    <button
      type="button"
      className="fd-mic"
      data-on={on || undefined}
      aria-pressed={on}
      aria-label={on ? "Stop and send" : "Talk: hold, or tap to start and stop"}
      title={on ? "Tap to send" : "Hold to talk, or tap to start and stop"}
      disabled={disabled || voice.state === "writing"}
      data-testid="finder-mic"
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        pressed.current = { at: Date.now(), was: on };
        if (!on) {
          onOpen();
          voice.start(false);
        }
      }}
      onPointerUp={() => {
        const p = pressed.current;
        pressed.current = null;
        if (!p) return;
        if (p.was || Date.now() - p.at > HOLD_MS) voice.stop();
      }}
      onContextMenu={(e) => e.preventDefault()}
      onClick={(e) => {
        if (e.detail !== 0) return; // pointer presses are handled above
        if (on) voice.stop();
        else {
          onOpen();
          voice.start(false);
        }
      }}
    >
      <Icon name="mic" />
    </button>
  );
}

function voiceNote(voice: Voice | null): string {
  const scrub = "Phone numbers and addresses are removed before the agent reads your words.";
  if (voice?.engine === "eleven") return `Voice by ElevenLabs. ${scrub}`;
  if (voice?.engine === "browser") return `Voice uses your browser's speech recognition. ${scrub}`;
  return "Phone numbers, emails, links and street addresses are removed before the agent reads your words.";
}

function Composer({
  value,
  onChange,
  onSend,
  busy,
  voice,
  placeholder,
  maxLength,
  onMicOpen,
  tools,
  note,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: (words: string) => void;
  busy: boolean;
  voice: Voice | null;
  placeholder: string;
  maxLength?: number;
  onMicOpen: () => void;
  tools?: ReactNode;
  note: string;
}) {
  const recording = voice?.state === "recording";
  const writing = voice?.state === "writing";
  const showMeter = (recording && voice?.engine === "eleven") || writing;
  const send = () => {
    const words = value.trim();
    if (!words || busy) return;
    onSend(words);
  };
  return (
    <div className="fd-composer" data-mic={voice?.state ?? "none"}>
      <form
        className="fd-form"
        aria-label="Send a message"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        {showMeter ? (
          <div className="fd-listen" role="status" data-testid="voice-listening">
            {recording ? (
              <>
                <LevelMeter level={voice!.level} />
                <span className="fd-listen-text">
                  Listening<span className="fd-listen-hint">: let go or tap the mic to send</span>
                </span>
                <button
                  type="button"
                  className="fd-listen-x"
                  aria-label="Cancel, don't send"
                  onClick={() => voice!.cancel()}
                >
                  <Icon name="close" />
                </button>
              </>
            ) : (
              <span className="fd-listen-text">Writing down what you said…</span>
            )}
          </div>
        ) : (
          <>
            <label className="sr-only" htmlFor="finder-note">
              Your message
            </label>
            <textarea
              id="finder-note"
              className="fd-input"
              rows={1}
              maxLength={maxLength}
              value={recording && voice?.engine === "browser" ? voice.interim || value : value}
              readOnly={recording}
              data-listening={recording || undefined}
              placeholder={recording ? "Listening…" : placeholder}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
            />
          </>
        )}
        {voice?.engine && <MicButton voice={voice} disabled={busy} onOpen={onMicOpen} />}
        <button
          type="submit"
          className="fd-send"
          disabled={!value.trim() || busy || recording || writing}
        >
          <span>Send</span>
          <Icon name="send" />
        </button>
      </form>
      {(voice?.error || voice?.note) && (
        <p className="fd-voice-msg" role="status">
          {voice.error ?? voice.note}
        </p>
      )}
      <div className="fd-tools">
        {tools}
        <p className="fd-fine fd-note" data-testid="voice-note">
          {note}
        </p>
      </div>
    </div>
  );
}

function EmptyThread({
  onExample,
  voice,
  busy,
  onMicOpen,
  lead,
}: {
  onExample: (words: string) => void;
  voice: Voice | null;
  busy: boolean;
  onMicOpen: () => void;
  lead: ReactNode;
}) {
  return (
    <div className="fd-empty-state" data-testid="finder-empty">
      <p className="fd-empty-kicker mono">Start here</p>
      <h2 className="fd-empty-title">What matters in your next home?</h2>
      <p className="fd-empty-lead">{lead}</p>
      <ul className="fd-examples" aria-label="Try one">
        {EXAMPLES.map((ex) => (
          <li key={ex}>
            <button
              type="button"
              className="fd-example"
              disabled={busy}
              onClick={() => onExample(ex)}
            >
              <span>&ldquo;{ex}&rdquo;</span>
              <Icon name="send" />
            </button>
          </li>
        ))}
      </ul>
      {voice?.engine && (
        <div className="fd-invite">
          <MicButton voice={voice} disabled={busy} onOpen={onMicOpen} />
          <p>
            <strong>Or just say it.</strong> Hold the mic and talk, or tap it once to start and
            again to send.
          </p>
        </div>
      )}
    </div>
  );
}

function useAutoScroll(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [dep]);
  return ref;
}

/** Narrow screens show one pane at a time: the chat, or what it knows and what leads. */
function PaneSwitch({
  pane,
  setPane,
  count,
}: {
  pane: "chat" | "list";
  setPane: (p: "chat" | "list") => void;
  count: number;
}) {
  return (
    <div className="fd-panes" role="group" aria-label="Show">
      <button type="button" aria-pressed={pane === "chat"} onClick={() => setPane("chat")}>
        Chat
      </button>
      <button type="button" aria-pressed={pane === "list"} onClick={() => setPane("list")}>
        Learned and picks{count > 0 && <span className="fd-count mono">{count}</span>}
      </button>
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
  const [pane, setPane] = useState<"chat" | "list">("chat");
  const sentOnce = useRef(false);

  // --- Voice: status from the server, read-aloud, talk mode.
  const [vs, setVs] = useState<VoiceStatus>({ tts: false, stt: true });
  const [readAloud, setReadAloud] = useState(loadReadAloud);
  const [talk, setTalk] = useState(false);
  const [speaking, setSpeaking] = useState<{ key: string; phase: "loading" | "playing" } | null>(
    null,
  );
  const [hint, setHint] = useState<string | null>(null);
  const { play, stop: stopVoice } = usePlayer();
  const clips = useRef(new Map<string, string>());
  const sayId = useRef(0);
  const flags = useRef({ talk, readAloud, tts: vs.tts });
  useEffect(() => {
    flags.current = { talk, readAloud, tts: vs.tts };
  });

  useEffect(() => {
    let on = true;
    void voiceStatus().then((s) => on && setVs(s));
    const held = clips.current;
    return () => {
      on = false;
      held.forEach((url) => URL.revokeObjectURL?.(url));
    };
  }, []);

  const hush = useCallback(() => {
    sayId.current++;
    stopVoice();
    setSpeaking(null);
  }, [stopVoice]);

  const say = useCallback(
    async (key: string, words: string, after?: () => void) => {
      const id = ++sayId.current;
      stopVoice();
      setSpeaking({ key, phase: "loading" });
      try {
        let url = clips.current.get(key);
        if (!url) {
          url = URL.createObjectURL(await synthesize(words));
          clips.current.set(key, url);
        }
        if (sayId.current !== id) return;
        setSpeaking({ key, phase: "playing" });
        await play(url, () => {
          if (sayId.current !== id) return;
          setSpeaking(null);
          after?.();
        });
      } catch (err) {
        if (sayId.current !== id) return;
        setSpeaking(null);
        if (err instanceof VoiceOff) setVs((v) => ({ ...v, tts: false }));
        after?.();
      }
    },
    [play, stopVoice],
  );

  const submitRef = useRef<(words: string) => void>(() => undefined);
  const endTalk = useCallback(
    (why?: string) => {
      flags.current.talk = false;
      setTalk(false);
      hush();
      if (why) setHint(why);
    },
    [hush],
  );
  const voice = useVoiceInput({
    server: vs.stt,
    onWords: (words) => submitRef.current(words),
    onSilence: () => {
      if (flags.current.talk) endTalk("Talk ended: I didn't hear anything.");
      else setHint("I didn't catch that. Hold the mic and try again.");
    },
  });
  const voiceStart = useRef(voice.start);
  useEffect(() => {
    voiceStart.current = voice.start;
  });
  const reopen = useCallback(() => {
    if (flags.current.talk) voiceStart.current(true);
  }, []);

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
      setHint(null);
      const fromMap = unsentSignals(loadFinderEvents());
      const signals = [...fromMap, ...extra];
      if (!words && signals.length === 0) return;
      if (words) push({ at: new Date().toISOString(), who: "you", text: words });
      setBusy({ since: Date.now(), what });
      try {
        const reply = await sendMessage(auth, words, signals);
        if (fromMap.length) setEvents(markSignalsSent());
        const at = new Date().toISOString();
        push({ at, who: "finder", text: reply.reply, by: reply.reply_by });
        const { talk: talking, readAloud: reading, tts } = flags.current;
        if (tts && (talking || reading)) void say(at, reply.reply, talking ? reopen : undefined);
        else if (talking) reopen();
        await refresh();
      } catch (err) {
        if (flags.current.talk) endTalk();
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
    [auth, endTalk, onOffline, push, refresh, reopen, say],
  );

  const submit = useCallback(
    (words: string) => {
      if (busy) return;
      hush(); // a new message stops whatever is being read
      setText("");
      setPane("chat");
      void run(words, [], "Reading your message and checking the places");
    },
    [busy, hush, run],
  );
  useEffect(() => {
    submitRef.current = submit;
  });

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
    hush();
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
  const scroller = useAutoScroll(`${items.length}:${open.length}:${busy ? 1 : 0}`);
  const empty = items.length === 0 && !busy;

  const startTalk = () => {
    hush();
    setHint(null);
    flags.current.talk = true;
    setTalk(true);
    setPane("chat");
    voice.start(true);
  };
  const phase =
    voice.state === "recording"
      ? "Listening"
      : voice.state === "writing"
        ? "Writing it down"
        : busy
          ? "Thinking"
          : speaking
            ? "Speaking"
            : "Your turn";

  const tools = (
    <>
      {talk ? (
        <div className="fd-talkbar" role="status" data-testid="talk-bar" data-phase={phase}>
          <span className="fd-talk-dot" aria-hidden="true" />
          <span className="fd-talk-phase">Talk mode · {phase}</span>
          <button
            type="button"
            className="fd-talk-end"
            onClick={() => {
              voice.cancel();
              endTalk();
            }}
          >
            <Icon name="stop" />
            End talk
          </button>
        </div>
      ) : (
        voice.engine && (
          <button
            type="button"
            className="fd-tool"
            onClick={startTalk}
            disabled={busy !== null || voice.state !== "idle"}
            title="Hands-free: it listens, answers out loud, then listens again"
          >
            <Icon name="talk" />
            Talk
          </button>
        )
      )}
      {vs.tts && !talk && (
        <button
          type="button"
          className="fd-tool"
          role="switch"
          aria-checked={readAloud}
          onClick={() => {
            const next = !readAloud;
            setReadAloud(next);
            saveReadAloud(next);
            if (!next) hush();
          }}
        >
          <Icon name="speaker" />
          Read replies aloud
          <span className="fd-switch" aria-hidden="true" />
        </button>
      )}
    </>
  );

  return (
    <>
      <FinderHead
        actions={
          <button
            type="button"
            className="fd-ghost"
            onClick={() => {
              voice.cancel();
              endTalk();
              onRestart();
            }}
            disabled={busy !== null}
          >
            Start over
          </button>
        }
      >
        <p className="fd-status" data-testid="finder-status">
          <SourceChip source={fs.source} />
          <span>
            {fs.mode === "deepagents"
              ? "Connected. Claude reads what you say and do; code checks every place and number."
              : "Connected, running on our rules: this server has no model key, so code writes every reply."}{" "}
            Nothing it learns applies until you say yes.
          </span>
        </p>
      </FinderHead>
      <PaneSwitch pane={pane} setPane={setPane} count={kept.length + fs.picks.length} />
      <div className="fd-app" data-pane={pane}>
        <section className="fd-main" aria-label="Conversation">
          <div className="fd-scroll" ref={scroller}>
            {empty ? (
              <EmptyThread
                onExample={submit}
                voice={voice}
                busy={busy !== null}
                onMicOpen={hush}
                lead={
                  <>
                    Say it or type it. It also learns from what you pass on here and on the{" "}
                    <a href="/map">map</a>, and keeps nothing until you say yes.
                  </>
                }
              />
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
                      {it.turn.who === "finder" && (
                        <span className="fd-kind mono">
                          Finder
                          {it.turn.by && (
                            <span className="fd-stamp" data-by={it.turn.by}>
                              {STAMP[it.turn.by]}
                            </span>
                          )}
                          {vs.tts && (
                            <button
                              type="button"
                              className="fd-play"
                              data-on={speaking?.key === it.turn.at || undefined}
                              aria-label={
                                speaking?.key === it.turn.at ? "Stop reading" : "Read this aloud"
                              }
                              onClick={() =>
                                speaking?.key === it.turn.at
                                  ? hush()
                                  : void say(it.turn.at, it.turn.text)
                              }
                            >
                              <Icon name={speaking?.key === it.turn.at ? "stop" : "speaker"} />
                            </button>
                          )}
                        </span>
                      )}
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
                {open.map((p) => (
                  <li className="fd-offer" key={p.id} data-testid="finder-proposal">
                    <span className="fd-offer-head">
                      <span className="fd-offer-kicker mono">Keep this?</span>
                      <span className="fd-stamp mono" data-by={p.chosen_by}>
                        {STAMP[p.chosen_by]}
                      </span>
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
                  </li>
                ))}
                {busy && (
                  <li className="fd-working" role="status" data-testid="finder-working">
                    <span className="fd-dots" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                    {busy.what}
                    {slow ? ". A full run with the model can take about half a minute." : "…"}
                  </li>
                )}
              </ol>
            )}
          </div>

          {(error || hint) && (
            <p className={error ? "fd-error" : "fd-hint"} role={error ? "alert" : "status"}>
              {error ?? hint}
            </p>
          )}

          <Composer
            value={text}
            onChange={setText}
            onSend={submit}
            busy={busy !== null}
            voice={voice}
            maxLength={500}
            placeholder="Under $1,500, no walk-ups, near downtown…"
            onMicOpen={hush}
            tools={tools}
            note={voiceNote(voice)}
          />
        </section>

        <aside className="fd-side" aria-label="What it knows and what leads">
          <section className="fd-block" aria-label="What I've learned about you">
            <h2 className="fd-h">What I&apos;ve learned</h2>
            {kept.length === 0 && lines.length === 0 ? (
              <p className="fd-empty" data-testid="learned-empty">
                Nothing yet. It notices what you pick and pass on, and keeps only what you say yes
                to.
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
                {kept.length > 0 && (
                  <p className="fd-fine">Kept items clear only with Start over, for now.</p>
                )}
              </>
            )}
          </section>

          <section className="fd-block" aria-label="Leading your list">
            <div className="fd-block-head">
              <h2 className="fd-h">Leading your list</h2>
              {fs.picks.length > 0 && <span className="fd-fine mono">{fs.picks.length} picks</span>}
            </div>
            {fs.picks.length === 0 ? (
              <p className="fd-empty" data-testid="picks-empty">
                {thread.some((t) => t.who === "finder")
                  ? "No place fits everything you kept. A higher budget would open more places."
                  : "Send a message and the Finder lines up three places here."}
              </p>
            ) : (
              <>
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
                <p className="fd-fine">
                  Code filters and orders every place. The Finder picks which lead and says why.
                </p>
              </>
            )}
          </section>

          <HowItDecided trace={fs.trace} />
        </aside>
      </div>
    </>
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
    pick.has_scan ? "3D scan" : null,
  ].filter((t): t is string => Boolean(t));
  const sample = source === "fixture";
  return (
    <li className="fd-pick" data-testid="finder-pick" data-has-scan={pick.has_scan || undefined}>
      <span className="fd-rank mono">{String(pick.rank).padStart(2, "0")}</span>
      <div className="fd-pick-body">
        <p className="fd-pick-line">{pick.line}</p>
        <p className="fd-pick-why">{pick.why}</p>
        <ul className="fd-tags" aria-label="On record">
          {tags.map((t) => (
            <li key={t} data-tag={t === "3D scan" ? "scan" : undefined}>
              {t}
            </li>
          ))}
          <li className="fd-tag-by" data-by={pick.chosen_by}>
            {STAMP[pick.chosen_by]}
          </li>
        </ul>
        <div className="fd-pick-acts">
          {sample ? (
            <span className="fd-fine" data-testid="pick-sample">
              Sample place by the team, not on the map
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
const LATEST_STEPS = 4;

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

function Step({ e }: { e: FinderTraceEvent }) {
  return (
    <li className="fd-step" data-kind={e.kind} data-testid="finder-step">
      <span className="fd-step-tag mono">{TRACE_TAG[e.kind] ?? e.kind}</span>
      <span className="fd-step-body">
        <span>{traceLine(e)}</span>
        {e.kind === "todo" && e.options.length > 0 && <Todo options={e.options} />}
        <span className="fd-step-by mono">{STAMP[e.chosen_by]}</span>
      </span>
    </li>
  );
}

function Todo({ options }: { options: string[] }) {
  return (
    <ul className="fd-todo">
      {options.map((o, i) => (
        <li key={i} data-done={o.startsWith("[x]") || undefined}>
          {o.replace(/^\[[x ]\]\s*/, "")}
        </li>
      ))}
    </ul>
  );
}

/** How the Finder decided: closed by default; the latest plan and steps, then all of them. */
export function HowItDecided({ trace }: { trace: FinderTraceEvent[] }) {
  const [all, setAll] = useState(false);
  if (trace.length === 0) return null;
  const plan = [...trace].reverse().find((e) => e.kind === "todo");
  const done = plan ? plan.options.filter((o) => o.startsWith("[x]")).length : 0;
  const latest = trace.filter((e) => e.kind !== "todo").slice(-LATEST_STEPS);
  return (
    <details className="fd-how" data-testid="finder-how">
      <summary>
        <span className="fd-how-title">How it decided</span>
        <span className="fd-how-meta mono">
          {plan ? `Plan ${done} of ${plan.options.length} · ` : ""}
          {trace.length} steps
        </span>
      </summary>
      <div className="fd-how-body">
        {all ? (
          <ol className="fd-steps">
            {trace.map((e) => (
              <Step key={e.seq} e={e} />
            ))}
          </ol>
        ) : (
          <>
            {plan && (
              <div className="fd-plan">
                <p className="fd-sub mono">Latest plan</p>
                <Todo options={plan.options} />
              </div>
            )}
            {latest.length > 0 && (
              <ol className="fd-steps" aria-label="Latest steps">
                {latest.map((e) => (
                  <Step key={e.seq} e={e} />
                ))}
              </ol>
            )}
          </>
        )}
        {trace.length > LATEST_STEPS && (
          <button type="button" className="fd-inline" onClick={() => setAll(!all)}>
            {all ? "Show the latest only" : `Show all ${trace.length} steps`}
          </button>
        )}
      </div>
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
  const [pane, setPane] = useState<"chat" | "list">("chat");
  const offer = nextOffer(events, learned.chips, learned.declined);
  const thread = [...events].reverse(); // oldest first, like a conversation
  const scroller = useAutoScroll(`${thread.length}:${offer?.id ?? ""}`);

  const keep = (next: { chips: Chip[]; declined: string[] }) => {
    setLearned(next);
    saveLearned(next);
  };
  const addChip = (chip: Chip) =>
    keep({ ...learned, chips: [...learned.chips.filter((c) => c.id !== chip.id), chip] });
  const note = (words: string) => {
    setEvents(recordFinderEvent("note", words));
    setText("");
  };
  const voice = useVoiceInput({ server: false, onWords: note });

  return (
    <>
      <FinderHead>
        <p className="fd-status">
          <span className="fd-off-chip mono">Offline</span>
          <span>Rules on this device keep what you say yes to. Nothing replies.</span>
        </p>
      </FinderHead>
      <PaneSwitch pane={pane} setPane={setPane} count={learned.chips.length} />
      <div className="fd-app" data-pane={pane}>
        <section className="fd-main" aria-label="Conversation">
          <div className="fd-scroll" ref={scroller}>
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
              <EmptyThread
                onExample={note}
                voice={voice}
                busy={false}
                onMicOpen={() => undefined}
                lead="Say it or type it. A code rule offers to keep what it can read, and keeps nothing until you say yes."
              />
            ) : (
              <ol className="fd-thread" aria-live="polite">
                {thread.map((e, i) => (
                  <li
                    key={`${e.at}-${i}`}
                    className="fd-msg"
                    data-kind={e.kind}
                    data-testid="finder-msg"
                  >
                    {e.kind !== "note" && (
                      <span className="fd-kind mono">{KIND_LABEL[e.kind] ?? e.kind}</span>
                    )}
                    <span className="fd-text">{e.text}</span>
                  </li>
                ))}
                {offer && (
                  <li className="fd-offer" data-testid="finder-offer">
                    <span className="fd-offer-head">
                      <span className="fd-offer-kicker mono">Keep this?</span>
                      <span className="fd-stamp mono">{OFFER_STAMP}</span>
                    </span>
                    <p className="fd-offer-text">Remember: {offer.label}?</p>
                    <div className="fd-offer-acts">
                      <button type="button" onClick={() => addChip(offer)}>
                        Yes, remember
                      </button>
                      <button
                        type="button"
                        className="fd-quiet"
                        onClick={() =>
                          keep({ ...learned, declined: [...learned.declined, offer.id] })
                        }
                      >
                        No
                      </button>
                    </div>
                  </li>
                )}
              </ol>
            )}
          </div>
          <Composer
            value={text}
            onChange={setText}
            onSend={note}
            busy={false}
            voice={voice}
            placeholder="No walk-ups, under $1,500, near downtown…"
            onMicOpen={() => undefined}
            note={voiceNote(voice)}
          />
        </section>
        <aside className="fd-side" aria-label="What it knows and what fits">
          <section className="fd-block" aria-label="What I've learned about you">
            <h2 className="fd-h">What I&apos;ve learned</h2>
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
            <p className="fd-fine">
              Rent, bedrooms, walk-ups, parking and pets narrow the places below. Anything else is
              kept as your note and does not filter yet.
            </p>
          </section>
          <section className="fd-block fd-places" aria-label="Places that fit">
            <PlacesStrip
              caseId={null}
              brief={briefFromChips(learned.chips)}
              heading="Places that fit what I know"
            />
          </section>
        </aside>
      </div>
    </>
  );
}

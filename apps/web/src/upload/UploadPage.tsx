import { useEffect, useReducer, useRef, useState } from "react";

import type { DataSource } from "../contracts";
import { SourceChip } from "../components/SourceChip";
import { TracePanel } from "../trace";
import {
  MODE,
  fetchApiSource,
  approveChallenge as defaultApprove,
  createCase as defaultCreateCase,
  getCaseStatus as defaultStatus,
  type ApproveChallenge,
  type CreateCase,
  type GetCaseStatus,
} from "./api";
import { initialState, reduce } from "./machine";
import { MAX_FILES, addFiles, classifyListingText, validateSubmission } from "./validate";
import "./upload.css";

export function goToCase(caseId: string) {
  window.history.pushState({}, "", `/case/${encodeURIComponent(caseId)}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

interface Props {
  createCase?: CreateCase;
  approveChallenge?: ApproveChallenge;
  getCaseStatus?: GetCaseStatus;
  pollMs?: number;
  navigate?: (caseId: string) => void;
  checkingMs?: number;
  waitingMs?: number;
  mode?: DataSource;
}

const STEPS = [
  { key: "reading", label: "Reading the listing" },
  { key: "checking", label: "Checking the building" },
  { key: "approval", label: "Your OK to message the poster" },
  { key: "waiting", label: "Waiting for the poster" },
] as const;

export function UploadPage({
  createCase = defaultCreateCase,
  approveChallenge = defaultApprove,
  getCaseStatus = defaultStatus,
  pollMs = 700,
  navigate = goToCase,
  checkingMs = 900,
  waitingMs = 1800,
  mode = MODE,
}: Props) {
  const [state, dispatch] = useReducer(reduce, initialState);
  // Until the API says what it serves, a wired page claims only FIXTURE, never LIVE.
  const [apiSource, setApiSource] = useState<DataSource>("fixture");
  useEffect(() => {
    if (mode !== "live") return;
    const ctrl = new AbortController();
    fetchApiSource(ctrl.signal)
      .then(setApiSource)
      .catch(() => {});
    return () => ctrl.abort();
  }, [mode]);
  const shownMode: DataSource = mode === "live" ? apiSource : mode;
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const removeButtons = useRef<Array<HTMLButtonElement | null>>([]);
  const focusAfterRemove = useRef<number | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  // Move focus to the new step's heading so keyboard and screen reader users follow along.
  useEffect(() => {
    heading.current?.focus();
  }, [state.step]);

  // Fixture mode paces the steps with timers. Live mode has no timers: the server already ran
  // the checks before POST /cases returned, so the approval step opens at once, and the waiting
  // step follows the real case until the server reports it done.
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
        // A failed poll is retried; the renter can also open the result by hand.
      }
      timer = setTimeout(poll, pollMs);
    };
    void poll();
    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [waitingCase, mode, getCaseStatus, pollMs]);

  useEffect(() => {
    if (state.step === "done") navigate(state.caseId);
  }, [state, navigate]);

  // After Remove, focus the Remove button that took the removed one's place, or the file input.
  useEffect(() => {
    const i = focusAfterRemove.current;
    if (i === null) return;
    focusAfterRemove.current = null;
    (removeButtons.current[i] ?? fileInput.current)?.focus();
  }, [files]);

  function take(list: FileList | File[] | null) {
    if (!list) return;
    const r = addFiles(files, Array.from(list));
    setFiles(r.files);
    setFileErrors(r.errors);
    setError(null);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validateSubmission({ text, files });
    if (!v.ok) {
      setError(v.error);
      return;
    }
    setError(null);
    dispatch({ type: "submit" });
    try {
      const made = await createCase({ link: v.link, text: v.text, files: v.files });
      dispatch({
        type: "created",
        caseId: made.case_id,
        challengeText: made.challenge_text,
        source: made.source,
      });
    } catch (err) {
      dispatch({
        type: "fail",
        message: err instanceof Error ? err.message : "Something went wrong. Try again.",
      });
    }
  }

  // Live mode tells the server what the renter decided, with the case token, before the page
  // moves on. Nothing moves on if the server refuses.
  // A ref guards the first click at once; a second click in the same tick must not post again.
  const deciding = useRef(false);
  const [busy, setBusy] = useState(false);
  async function decide(decision: "send" | "cancel") {
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

  async function copy(message: string) {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const kind = classifyListingText(text).kind;
  const errorId = "upload-error";

  if (state.step === "input") {
    return (
      <div className="card-page upload" data-testid="upload-page">
        <header className="masthead">
          <span className="wordmark">SNAPBACK</span>
          <SourceChip source={shownMode} />
        </header>
        <form className="upload-body" onSubmit={onSubmit} noValidate>
          <h1 ref={heading} tabIndex={-1}>
            Check a rental before you pay.
          </h1>
          <p className="upload-lead">
            Paste the listing link, or add screenshots of it. We read it and check the place.
          </p>

          <label htmlFor="listing" className="upload-label">
            Listing link or text
          </label>
          <textarea
            id="listing"
            className="upload-input"
            rows={3}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setError(null);
            }}
            placeholder="https://www.zillow.com/homedetails/..."
            aria-describedby={error ? errorId : "listing-hint"}
            aria-invalid={error ? true : undefined}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
          />
          <p id="listing-hint" className="upload-hint">
            {kind === "text"
              ? "Reading this as listing text."
              : "A link, or paste the listing text."}
          </p>

          <div
            className={`upload-drop${dragging ? " is-dragging" : ""}`}
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
            <label htmlFor="photos" className="upload-label">
              Screenshots or photos (optional)
            </label>
            <input
              ref={fileInput}
              id="photos"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
              multiple
              onChange={(e) => {
                take(e.target.files);
                e.target.value = "";
              }}
              aria-describedby="photos-hint"
            />
            <p id="photos-hint" className="upload-hint">
              Drop them here or choose files. JPG, PNG, WebP or HEIC, up to 10 MB each, {MAX_FILES}{" "}
              at most.
            </p>
          </div>

          {files.length > 0 && (
            <ul className="upload-files" aria-label="Added photos">
              {files.map((f, i) => (
                <li key={`${f.name}-${f.size}`}>
                  <span>{f.name}</span>
                  <button
                    type="button"
                    className="upload-remove"
                    aria-label={`Remove ${f.name}`}
                    ref={(el) => {
                      removeButtons.current[i] = el;
                    }}
                    onClick={() => {
                      focusAfterRemove.current = i;
                      removeButtons.current.length = files.length - 1;
                      setFiles(files.filter((g) => g !== f));
                    }}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          {fileErrors.length > 0 && (
            <ul className="upload-errors" role="alert">
              {fileErrors.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          {error && (
            <p id={errorId} className="upload-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="upload-submit">
            Check this listing
          </button>
          <p className="upload-hint">
            SNAPBACK never texts anyone for you. You approve and send any message yourself.
          </p>
        </form>
      </div>
    );
  }

  if (state.step === "error") {
    return (
      <div className="card-page upload" data-testid="upload-page">
        <header className="masthead">
          <span className="wordmark">SNAPBACK</span>
          <SourceChip source={shownMode} />
        </header>
        <div className="upload-body">
          <h1 ref={heading} tabIndex={-1}>
            That did not go through
          </h1>
          <p className="upload-error" role="alert">
            {state.message}
          </p>
          <p className="upload-hint">Your link and photos are still here. Nothing was sent.</p>
          <button
            type="button"
            className="upload-submit"
            onClick={() => dispatch({ type: "retry" })}
          >
            Back to the form
          </button>
        </div>
      </div>
    );
  }

  const activeIndex = STEPS.findIndex((s) => s.key === state.step);
  const source: DataSource = "source" in state ? state.source : shownMode;

  return (
    <div className="card-page upload" data-testid="upload-page">
      <header className="masthead">
        <span className="wordmark">SNAPBACK</span>
        <SourceChip source={source} />
      </header>
      <div className="upload-body">
        <ol className="upload-steps" aria-label="Progress">
          {STEPS.map((s, i) => {
            const status =
              state.step === "done" || i < activeIndex
                ? "done"
                : i === activeIndex
                  ? "active"
                  : "todo";
            return (
              <li
                key={s.key}
                data-status={status}
                aria-current={status === "active" ? "step" : undefined}
              >
                <span className="upload-step-mark" aria-hidden="true">
                  {status === "done" ? "✓" : i + 1}
                </span>
                {s.label}
                <span className="sr-only">
                  {status === "done" ? " (done)" : status === "active" ? " (now)" : " (next)"}
                </span>
              </li>
            );
          })}
        </ol>

        <div aria-live="polite">
          {state.step === "reading" && (
            <>
              <h1 ref={heading} tabIndex={-1}>
                Reading the listing
              </h1>
              <p className="upload-lead">This takes a few seconds. You can leave this tab open.</p>
            </>
          )}
          {state.step === "checking" && (
            <>
              <h1 ref={heading} tabIndex={-1}>
                Checking the building
              </h1>
              <p className="upload-lead">Looking up the place on the listing.</p>
            </>
          )}
          {state.step === "waiting" && (
            <>
              <h1 ref={heading} tabIndex={-1}>
                Waiting for the poster
              </h1>
              <p className="upload-lead">
                No reply yet means HOLD, not a failure. You can open your result now; it updates
                when they answer.
              </p>
              {mode === "live" && <TracePanel caseId={state.caseId} mode="live" />}
              <button
                type="button"
                className="upload-submit"
                onClick={() => dispatch({ type: "done" })}
              >
                See my result now
              </button>
            </>
          )}
          {state.step === "done" && (
            <>
              <h1 ref={heading} tabIndex={-1}>
                Opening your result
              </h1>
            </>
          )}
        </div>

        {state.step === "approval" && (
          <section aria-labelledby="approve-title">
            <h1 id="approve-title" ref={heading} tabIndex={-1}>
              Send this to the poster
            </h1>
            <p className="upload-lead">
              A live check asks the poster for a fresh photo from the unit. Nothing is sent for you.
              Copy this message and send it yourself, then tell us you did.
            </p>
            <label htmlFor="challenge" className="upload-label">
              Message to forward
            </label>
            <textarea
              id="challenge"
              className="upload-input"
              rows={5}
              readOnly
              value={state.challengeText}
              onFocus={(e) => e.currentTarget.select()}
            />
            <div className="upload-actions">
              <button
                type="button"
                className="upload-secondary"
                onClick={() => copy(state.challengeText)}
              >
                Copy message
              </button>
              <span role="status" className="upload-hint">
                {copied ? "Copied." : ""}
              </span>
            </div>
            <div className="upload-actions">
              <button
                type="button"
                className="upload-submit"
                disabled={busy}
                onClick={() => void decide("send")}
              >
                I approve it and I will send it
              </button>
              <button
                type="button"
                className="upload-secondary"
                disabled={busy}
                onClick={() => void decide("cancel")}
              >
                Skip the live check
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";

import "../ui/ui.css";
import { ADS, agrees, mood, score, scoreLine, type Call, type SpotAd } from "./model";
import "./spot.css";

// /spot: a 30-second game for the judging table. Four composed ads, one per screen; the player
// taps Looks fine or Hold off; the reveal shows what SNAPBACK's text rules caught, with the card's
// own reason lines. Every ad is SYNTHETIC and every verdict is a FIXTURE result (see model.ts).

function AdBody({ ad, reveal }: { ad: SpotAd; reveal: boolean }) {
  return (
    <p className="sp-text">
      {ad.segs.map((s, i) =>
        s.rules && reveal ? (
          <mark key={i} className="sp-mark" data-on="true">
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}{" "}
      <span className="sp-phone ui-mono">Text {ad.phone}</span>
    </p>
  );
}

function AdCard({ ad, reveal = false }: { ad: SpotAd; reveal?: boolean }) {
  return (
    <article className="sp-ad" aria-label={`Composed ad: ${ad.place}`}>
      <header className="sp-ad-head">
        <p className="sp-price">{ad.price}</p>
        <p className="sp-place">{ad.place}</p>
        <span className="sp-stamp ui-mono">SYNTHETIC</span>
      </header>
      <AdBody ad={ad} reveal={reveal} />
    </article>
  );
}

function Intro({ onStart }: { onStart: () => void }) {
  return (
    <section className="sp-intro" data-testid="spot-intro" aria-labelledby="sp-intro-h">
      <p className="sp-kicker ui-mono">30 seconds · 4 ads</p>
      <h1 id="sp-intro-h" className="sp-title">
        Spot the scam.
      </h1>
      <p className="sp-lede">
        Four rental ads. Two are honest, two show scam patterns. Tap <strong>Looks fine</strong> or{" "}
        <strong>Hold off</strong> on each, then see what SNAPBACK caught.
      </p>
      <button type="button" className="sp-go" onClick={onStart} data-testid="spot-start">
        Start
      </button>
      <p className="sp-fine ui-mono">
        Every ad is SYNTHETIC: composed by the team, with 555 numbers and no real address.
      </p>
    </section>
  );
}

function Play({
  index,
  ad,
  onAnswer,
}: {
  index: number;
  ad: SpotAd;
  onAnswer: (call: Call) => void;
}) {
  const head = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    head.current?.focus({ preventScroll: true });
  }, [index]);
  return (
    <section className="sp-play" data-testid="spot-play" aria-labelledby="sp-step">
      <div className="sp-progress">
        <h2 id="sp-step" ref={head} tabIndex={-1} className="sp-step ui-mono">
          Ad {index + 1} of {ADS.length}
        </h2>
        <ol className="sp-pips" aria-hidden="true">
          {ADS.map((a, i) => (
            <li key={a.id} data-state={i < index ? "done" : i === index ? "now" : "next"} />
          ))}
        </ol>
      </div>
      <div className="sp-slide" key={ad.id}>
        <AdCard ad={ad} />
        <p className="sp-ask">Would you send money or papers to this poster?</p>
        <div className="sp-buttons">
          <button
            type="button"
            className="sp-btn"
            data-call="fine"
            onClick={() => onAnswer("fine")}
            data-testid="spot-fine"
          >
            Looks fine
          </button>
          <button
            type="button"
            className="sp-btn"
            data-call="hold"
            onClick={() => onAnswer("hold")}
            data-testid="spot-hold"
          >
            Hold off
          </button>
        </div>
      </div>
    </section>
  );
}

function Row({ ad, call, i }: { ad: SpotAd; call: Call; i: number }) {
  const right = agrees(ad, call);
  const you = call === "hold" ? "Hold off" : "Looks fine";
  return (
    <li
      className="sp-row"
      data-testid={`spot-row-${ad.id}`}
      data-kind={ad.kind}
      style={{ "--i": i } as React.CSSProperties}
    >
      <AdCard ad={ad} reveal />
      <div className="sp-verdict" data-call={ad.verdict}>
        <p className="sp-vline">
          <span className="sp-chip" data-call={ad.verdict}>
            SNAPBACK: {ad.verdict === "hold" ? "Hold off" : "Looks fine"}
          </span>
          <span className="sp-you" data-right={right ? "true" : "false"}>
            You: {you}. {right ? "Match." : "Different call."}
          </span>
        </p>
        <p className="sp-head">
          {ad.kind === "pattern" ? "This ad shows scam patterns. " : ""}
          {ad.headline}
        </p>
        {ad.lines.length > 0 && (
          <ul className="sp-lines" aria-label="The card's reason lines">
            {ad.lines.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        )}
        {ad.note && <p className="sp-note">{ad.note}</p>}
      </div>
    </li>
  );
}

function Reveal({ answers, onAgain }: { answers: Call[]; onAgain: () => void }) {
  const head = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    head.current?.focus({ preventScroll: true });
    window.scrollTo?.({ top: 0 });
  }, []);
  const s = score(answers);
  return (
    <section className="sp-reveal" data-testid="spot-reveal" aria-labelledby="sp-score">
      <div className="sp-score">
        <p className="sp-kicker ui-mono">Your score</p>
        <h1 id="sp-score" ref={head} tabIndex={-1} className="sp-big" data-testid="spot-score">
          <span className="sp-num">{s.caught}</span>
          <span className="sp-of"> of {s.patterns}</span>
        </h1>
        <p className="sp-line" data-testid="spot-line">
          {scoreLine(s)}
        </p>
        <p className="sp-mood">{mood(s)}</p>
        <p className="sp-fine ui-mono" data-testid="spot-honest">
          Honest ads you let through: {s.cleared} of {s.honest}. SNAPBACK's text rules:{" "}
          {s.snapbackCleared} of {s.honest}. (n={s.n}, SYNTHETIC ads, FIXTURE verdicts)
        </p>
      </div>
      <ol className="sp-rows">
        {ADS.map((ad, i) => (
          <Row key={ad.id} ad={ad} call={answers[i] ?? "fine"} i={i} />
        ))}
      </ol>
      <p className="sp-scope">
        This is the text check only. On a real ad the card also reads the building's record and the
        photos, and a rule hit never says anyone did anything wrong; it says the ad shows a pattern
        worth a second look.
      </p>
      <div className="sp-end">
        <button
          type="button"
          className="sp-btn"
          data-call="again"
          onClick={onAgain}
          data-testid="spot-again"
        >
          Play again
        </button>
        <a className="sp-btn sp-link" href="/home">
          Check a real ad
        </a>
      </div>
    </section>
  );
}

export function SpotPage() {
  const [answers, setAnswers] = useState<Call[]>([]);
  const [started, setStarted] = useState(false);
  const done = answers.length >= ADS.length;
  const ad = ADS[answers.length];
  return (
    <div className="sp" data-testid="spot">
      {!started ? (
        <Intro onStart={() => setStarted(true)} />
      ) : done ? (
        <Reveal
          answers={answers}
          onAgain={() => {
            setAnswers([]);
          }}
        />
      ) : (
        ad && (
          <Play
            index={answers.length}
            ad={ad}
            onAnswer={(c) => setAnswers((a) => (a.length < ADS.length ? [...a, c] : a))}
          />
        )
      )}
    </div>
  );
}

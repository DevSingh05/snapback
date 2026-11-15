import { useEffect, useState } from "react";

import amazonShot from "../assets/hood/show-onebox.webp";
import arlequinShot from "../assets/hood/show-rings.webp";
import costarShot from "../assets/hood/show-scan.webp";
import langchainShot from "../assets/hood/show-crew.webp";
import "../ui/ui.css";
import {
  LABEL_HINT,
  MERGED,
  nText,
  shownPanels,
  TRUST,
  type DataLabel,
  type Measured,
  type Panel,
  type ShowLink,
  type Switches,
} from "./panels";
import "./hood.css";

// /under-the-hood: a map for a judge at the table. One section per sponsor track, read top to
// bottom in five seconds: what it does for the person, the measured number, what of theirs we
// used, and a picture of the screen that opens it. All of the content lives in panels.ts.

const LABELS: DataLabel[] = ["LIVE", "FIXTURE", "SYNTHETIC"];

/** Crops of the app's own screens in fixture mode: team-made sample data, never sponsor data. */
const SHOTS: Record<string, string> = {
  costar: costarShot,
  langchain: langchainShot,
  arlequin: arlequinShot,
  amazon: amazonShot,
};

// The sample thread, drawn. The reply lines are the sidecar's and the card's own words
// (apps/sidecar/src/handler.ts, fixtures/contracts/card_hold.json); the ad is the team's sample.
const THREAD: Array<{ from: "renter" | "snapback"; text: string }> = [
  { from: "renter", text: "Is this one real? They want the deposit by Zelle before a viewing." },
  {
    from: "snapback",
    text: "Got it. Checking this against CoStar's record before you pay anyone. About a minute.",
  },
  { from: "snapback", text: "Hold off: it asks for money before you've seen the place." },
];

function DataTag({ label }: { label: DataLabel }) {
  return (
    <span className="ui-tag uh-tag" data-label={label} title={LABEL_HINT[label]}>
      {label}
    </span>
  );
}

function Figure({ m }: { m: Measured }) {
  return (
    <div className="uh-num" data-testid="hood-number">
      <dd>{m.value}</dd>
      <dt>{m.what}</dt>
      <p className="uh-n">
        <span className="ui-mono">{nText(m)}</span>
        <DataTag label={m.label} />
      </p>
    </div>
  );
}

function Thread() {
  return (
    <span className="uh-thread" role="img" aria-label="A sample iMessage thread with SNAPBACK">
      {THREAD.map((line) => (
        <span key={line.text} className="uh-bubble" data-from={line.from} aria-hidden="true">
          {line.text}
        </span>
      ))}
    </span>
  );
}

function More({ link }: { link: ShowLink }) {
  return (
    <li>
      <a href={link.href}>{link.label}</a>
      <DataTag label={link.data} />
    </li>
  );
}

function PanelView({ panel }: { panel: Panel }) {
  const title = `uh-${panel.id}-title`;
  // Nothing measured yet: the line about where it runs live takes the numbers' place.
  const lead = panel.numbers.length === 0 && Boolean(panel.aside);
  return (
    <section
      id={panel.id}
      className="uh-panel"
      aria-labelledby={title}
      data-testid={`hood-${panel.id}`}
    >
      <header className="uh-who">
        <span className="uh-mark ui-mono" aria-hidden="true">
          {panel.mark}
        </span>
        <h2 id={title} className="uh-sponsor">
          {panel.sponsor}
        </h2>
        <p className="uh-track ui-mono">{panel.track}</p>
      </header>
      <p className="uh-does">{panel.does}</p>
      {panel.numbers.length > 0 && (
        <dl className="uh-nums" aria-label="What we measured">
          {panel.numbers.map((m) => (
            <Figure key={m.value + m.what} m={m} />
          ))}
        </dl>
      )}
      {lead && <p className="uh-nums uh-live">{panel.aside}</p>}
      <ul className="uh-used" aria-label="What we used">
        {panel.used.map((u) => (
          <li key={u.tech}>
            <strong>{u.tech}</strong>
            <span>{u.text}</span>
          </li>
        ))}
      </ul>
      <div className="uh-see">
        <a className="uh-show" href={panel.show.href}>
          <span className="uh-shot">
            {panel.shot.kind === "thread" ? (
              <Thread />
            ) : (
              <img
                src={SHOTS[panel.id]}
                alt={panel.shot.alt}
                width={800}
                height={450}
                loading="lazy"
                decoding="async"
              />
            )}
            <span className="uh-stamp ui-mono" aria-hidden="true">
              {panel.shot.kind === "thread" ? "Sample thread" : "The screen it opens"}
            </span>
          </span>
          <span className="uh-go">
            <span>{panel.show.label}</span>
            <span className="uh-arrow" aria-hidden="true">
              →
            </span>
          </span>
        </a>
        <p className="uh-opens">
          <DataTag label={panel.show.data} />
          <span className="ui-mono uh-path">{panel.show.href}</span>
        </p>
        {panel.more.length > 0 && (
          <ul className="uh-more" aria-label="Also see">
            {panel.more.map((l) => (
              <More key={l.href} link={l} />
            ))}
          </ul>
        )}
        {panel.aside && !lead && <p className="uh-aside">{panel.aside}</p>}
      </div>
    </section>
  );
}

/** Which sponsor's section is under the index right now, so its chip can say so. */
function useHere(ids: string[]): string | null {
  const [here, setHere] = useState<string | null>(null);
  const key = ids.join(" ");
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        setHere(key.split(" ").find((id) => seen.get(id)) ?? null);
      },
      // A band across the upper middle of the screen: the section crossing it is "here".
      { rootMargin: "-30% 0px -60% 0px" },
    );
    for (const id of key.split(" ")) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [key]);
  return here;
}

function TrustTable() {
  return (
    <section
      id="trust"
      className="uh-trust"
      aria-labelledby="uh-trust-title"
      data-testid="hood-trust"
    >
      <h2 id="uh-trust-title" className="uh-sponsor">
        Why trust this
      </h2>
      <p className="uh-lede">
        Our method beside a simple baseline, on the same set. The ring sets are SYNTHETIC: rings we
        seeded ourselves, so they show the method works on rings shaped like these, not how often it
        is right on real listings. Where no baseline was measured, we say so.
      </p>
      <div className="uh-trust-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Test</th>
              <th scope="col">SNAPBACK</th>
              <th scope="col">Baseline, same set</th>
              <th scope="col">n and data</th>
            </tr>
          </thead>
          <tbody>
            {TRUST.map((r) => (
              <tr key={r.eval} data-testid="hood-trust-row">
                <th scope="row">{r.eval}</th>
                <td>{r.ours}</td>
                <td>
                  {r.baseline === null ? (
                    <span className="uh-none">None measured</span>
                  ) : (
                    <>
                      {r.baseline}
                      <span className="uh-baseline-is"> ({r.baselineIs})</span>
                    </>
                  )}
                </td>
                <td>
                  <span className="ui-mono">
                    n = {r.n.toLocaleString("en-US")} {r.unit}
                  </span>{" "}
                  <DataTag label={r.label} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function HoodPage({ switches = MERGED }: { switches?: Switches } = {}) {
  const panels = shownPanels(switches);
  const here = useHere(panels.map((p) => p.id));
  return (
    <div className="uh" data-testid="hood">
      <header className="uh-head">
        <h1 className="uh-title">Under the hood</h1>
        <p className="uh-lede">
          What SNAPBACK is built on, what we measured, and the exact screen where you can see each
          part working.
        </p>
        <ul className="uh-key" aria-label="What the labels mean">
          {LABELS.map((l) => (
            <li key={l}>
              <DataTag label={l} />
              <span>{LABEL_HINT[l]}</span>
            </li>
          ))}
        </ul>
      </header>
      <nav className="uh-jump" aria-label="Sponsors">
        {panels.map((p) => (
          <a key={p.id} href={`#${p.id}`} aria-current={here === p.id ? "true" : undefined}>
            <span className="uh-mark uh-mark-sm ui-mono" aria-hidden="true">
              {p.mark}
            </span>
            {p.sponsor}
          </a>
        ))}
      </nav>
      {panels.map((p) => (
        <PanelView key={p.id} panel={p} />
      ))}
      <TrustTable />
      <p className="uh-foot">
        Every figure here was measured by the team, with its n beside it. Nothing from CoStar's
        record is printed on this page. Want to try your own eye first?{" "}
        <a href="/spot">Spot the scam in 30 seconds</a>.
      </p>
    </div>
  );
}

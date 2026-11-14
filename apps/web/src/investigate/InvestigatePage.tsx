import { useEffect, useState } from "react";

import { apiBase } from "../api";
import { layoutGraph, timeScale } from "./layout";
import type { Answer, Evidence, Finding, RingResponse, RingsResponse, Score } from "./types";
import "./investigate.css";

const GRAPH_SIZE = 560;

function base(): string {
  return apiBase() ?? "/api";
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base()}${path}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as T;
}

export function percent(x: number): string {
  return `${Math.round(x * 100)}%`;
}

// ---- evidence ---------------------------------------------------------------------------

export function EvidenceList({
  items,
  onPick,
}: {
  items: Evidence[];
  onPick: (adId: number) => void;
}) {
  return (
    <ul className="inv-evidence">
      {items.map((e, i) => (
        <li key={`${e.ad_id}-${i}`}>
          <button type="button" className="inv-ad-chip" onClick={() => onPick(e.ad_id)}>
            ad {e.ad_id}
          </button>
          {e.span ? <q>{e.span}</q> : null}
          {e.note ? <span className="inv-note">{e.note}</span> : null}
          {e.phone ? <code>{e.phone}</code> : null}
          {e.photo_ids.length ? (
            <code className="inv-photos">
              {e.photo_ids.slice(0, 3).join(" ")}
              {e.photo_ids.length > 3 ? ` +${e.photo_ids.length - 3}` : ""}
            </code>
          ) : null}
          {e.rule_id ? <span className="inv-rule">rule {e.rule_id}</span> : null}
          {e.score != null ? <span className="inv-score">match {e.score.toFixed(2)}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function FindingCard({ finding, onPick }: { finding: Finding; onPick: (adId: number) => void }) {
  return (
    <article className="inv-finding" data-kind={finding.kind}>
      <header>
        <h3>{finding.title}</h3>
        <span
          className="inv-strength"
          title="How strongly this signal links the ads. Not a probability."
        >
          link strength {finding.score.toFixed(2)}
        </span>
      </header>
      <p>{finding.summary}</p>
      <details>
        <summary>Show the evidence ({finding.evidence.length})</summary>
        <EvidenceList items={finding.evidence} onPick={onPick} />
      </details>
    </article>
  );
}

// ---- the ring graph ---------------------------------------------------------------------

export function RingGraph({
  data,
  selected,
  onPick,
}: {
  data: RingResponse;
  selected: number | null;
  onPick: (adId: number) => void;
}) {
  const placed = layoutGraph(data.graph.nodes, data.graph.edges, GRAPH_SIZE);
  const ring = data.ring;
  return (
    <figure className="inv-graph">
      <svg
        viewBox={`0 0 ${GRAPH_SIZE} ${GRAPH_SIZE}`}
        role="img"
        aria-label={`${ring.label}: ${ring.ad_ids.length} ads joined by shared numbers, photos and wording`}
      >
        <g className="inv-edges">
          {data.graph.edges.map((e, i) => {
            const a = placed.get(e.source);
            const b = placed.get(e.target);
            if (!a || !b) return null;
            const hot = selected != null && e.source === `ad-${selected}`;
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className={hot ? "inv-edge inv-edge-hot" : "inv-edge"}
              />
            );
          })}
        </g>
        <g>
          {[...placed.values()]
            .filter((n) => n.type !== "ad")
            .map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.x} ${n.y})`}
                className={`inv-node inv-${n.type}`}
              >
                <title>{`${n.type === "phone" ? "number " : n.type === "photo" ? "photo-set " : "wording "}${n.label}`}</title>
                {n.type === "phone" ? (
                  <polygon points="0,-9 9,0 0,9 -9,0" />
                ) : n.type === "photo" ? (
                  <polygon points="0,-10 9,7 -9,7" />
                ) : (
                  <polygon points="-5,-9 5,-9 10,0 5,9 -5,9 -10,0" />
                )}
              </g>
            ))}
        </g>
        <g>
          {[...placed.values()]
            .filter((n) => n.type === "ad")
            .map((n) => {
              const id = Number(n.label);
              const on = selected === id;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x} ${n.y})`}
                  className={on ? "inv-node inv-ad inv-selected" : "inv-node inv-ad"}
                  onClick={() => onPick(id)}
                  role="button"
                  tabIndex={0}
                  aria-label={`ad ${id}, ${n.date ?? ""}`}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter" || ev.key === " ") onPick(id);
                  }}
                >
                  <rect
                    x={on ? -9 : -6}
                    y={on ? -9 : -6}
                    width={on ? 18 : 12}
                    height={on ? 18 : 12}
                  />
                  <text y={on ? -14 : -10} textAnchor="middle">
                    {n.label}
                  </text>
                </g>
              );
            })}
        </g>
      </svg>
      <figcaption className="inv-legend">
        <span className="inv-key inv-key-ad">ad</span>
        <span className="inv-key inv-key-phone">shared number</span>
        <span className="inv-key inv-key-photo">shared photo-set</span>
        <span className="inv-key inv-key-phrase">shared wording</span>
      </figcaption>
    </figure>
  );
}

// ---- the timeline strip -----------------------------------------------------------------

export function TimelineStrip({
  data,
  selected,
  onPick,
}: {
  data: RingResponse;
  selected: number | null;
  onPick: (adId: number) => void;
}) {
  const ring = data.ring;
  const at = timeScale(ring.first_seen, ring.last_seen);
  const W = 960;
  const H = 150;
  const base = 104;
  const max = Math.max(...ring.weekly.map(([, n]) => n), 1);
  const adDate = new Map(data.ads.map((a) => [a.id, a.posted_at]));
  const phoneEvents = ring.timeline.filter((e) => e.kind === "new_phone" || e.kind === "first_ad");
  return (
    <figure className="inv-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${ring.label} timeline`}>
        {ring.weekly.map(([week, n]) => {
          const x = at(week) * W;
          const h = (n / max) * 52;
          return (
            <rect key={week} className="inv-week" x={x} y={base - h} width={W / 52} height={h} />
          );
        })}
        <line className="inv-axis" x1="0" x2={W} y1={base} y2={base} />
        {ring.ad_ids.map((id) => {
          const d = adDate.get(id);
          if (!d) return null;
          return (
            <rect
              key={id}
              className={selected === id ? "inv-tick inv-tick-on" : "inv-tick"}
              x={at(d) * W - 2}
              y={base + 6}
              width="4"
              height={selected === id ? 18 : 12}
              onClick={() => onPick(id)}
            >
              <title>{`ad ${id}, ${d}`}</title>
            </rect>
          );
        })}
        {phoneEvents.map((e) => (
          <g key={`${e.ad_id}-${e.kind}`} transform={`translate(${at(e.date) * W} ${base - 66})`}>
            <polygon className="inv-phone-mark" points="0,-6 6,0 0,6 -6,0" />
            <line className="inv-axis" x1="0" x2="0" y1="6" y2="60" />
            <title>{`${e.date}: ${e.detail}`}</title>
          </g>
        ))}
        <text className="inv-axis-label" x="0" y={H - 4}>
          {ring.first_seen}
        </text>
        <text className="inv-axis-label" x={at(ring.last_seen) * W} y={H - 4} textAnchor="end">
          {ring.last_seen}
        </text>
      </svg>
      <figcaption className="inv-legend">
        <span className="inv-key inv-key-week">ads per week</span>
        <span className="inv-key inv-key-phone">a new number goes live</span>
        <span className="inv-key inv-key-ad">each ad</span>
      </figcaption>
    </figure>
  );
}

// ---- the ask box ------------------------------------------------------------------------

function AskPanel({
  examples,
  onPick,
  ask,
}: {
  examples: string[];
  onPick: (adId: number) => void;
  ask: (q: string) => Promise<Answer>;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const run = async (q: string) => {
    if (!q.trim()) return;
    setBusy(true);
    setFailed(false);
    try {
      setAnswer(await ask(q));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="inv-ask" aria-label="Ask the evidence graph">
      <h2>Ask the evidence</h2>
      <p className="inv-sub">
        Answers come only from the link graph, and cite the ads behind them. No evidence, no answer.
      </p>
      <form
        onSubmit={(ev) => {
          ev.preventDefault();
          void run(question);
        }}
      >
        <input
          value={question}
          onChange={(ev) => setQuestion(ev.target.value)}
          placeholder="Which ads share photos with ad 57?"
          maxLength={300}
          aria-label="Question"
        />
        <button type="submit" disabled={busy}>
          Ask
        </button>
      </form>
      <div className="inv-examples">
        {examples.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => {
              setQuestion(q);
              void run(q);
            }}
          >
            {q}
          </button>
        ))}
      </div>
      {failed ? <p className="inv-error">The question did not go through. Try again.</p> : null}
      {answer ? (
        <div className="inv-answer" data-grounded={answer.grounded}>
          <p>{answer.answer}</p>
          {answer.grounded ? (
            <details open>
              <summary>Show the evidence ({answer.evidence.length})</summary>
              <EvidenceList items={answer.evidence} onPick={onPick} />
            </details>
          ) : (
            <p className="inv-sub">Nothing in the graph backs an answer, so none is given.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}

// ---- the page ---------------------------------------------------------------------------

function ScoreRow({ label, score, tone }: { label: string; score: Score; tone: string }) {
  return (
    <div className={`inv-score-row inv-${tone}`}>
      <h3>{label}</h3>
      <dl>
        <div>
          <dt>rings recovered</dt>
          <dd>{score.rings_recovered}</dd>
        </div>
        <div>
          <dt>ring recall</dt>
          <dd>{percent(score.ring_recall)}</dd>
        </div>
        <div>
          <dt>ads found</dt>
          <dd>{percent(score.ad_recall)}</dd>
        </div>
        <div>
          <dt>honest ads wrongly flagged</dt>
          <dd>{percent(1 - score.ad_precision)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function InvestigateView({
  rings,
  ring,
  ringId,
  onRing,
  selected,
  onPick,
  ask,
}: {
  rings: RingsResponse;
  ring: RingResponse | null;
  ringId: string;
  onRing: (id: string) => void;
  selected: number | null;
  onPick: (adId: number) => void;
  ask: (q: string) => Promise<Answer>;
}) {
  const m = rings.metrics;
  const pickedAd = ring?.ads.find((a) => a.id === selected) ?? null;
  return (
    <div className="inv-page">
      <header className="inv-head">
        <div>
          <p className="inv-eyebrow">Investigator view</p>
          <h1>The ring behind the ads</h1>
          <p className="inv-sub">
            One renter&apos;s check answers one ad. An investigator needs to see who is behind many.
          </p>
        </div>
        <div className="inv-chips">
          <span className="inv-chip inv-chip-synth">SYNTHETIC DATA</span>
          <span className="inv-chip">FIXTURE</span>
        </div>
      </header>

      <section className="inv-measure" aria-label="Measured result">
        <p className="inv-sub">
          Measured on {m.n_ads} synthetic ads with {m.n_true_rings} seeded rings, scored against the
          seeded answer key. A ring counts as recovered when one group holds 70% of its ads and is
          70% that ring.
        </p>
        <div className="inv-scores">
          <ScoreRow label="This pipeline" score={m.pipeline} tone="pipe" />
          <ScoreRow
            label="Keyword search, then group by exact number or photo"
            score={m.keyword_baseline}
            tone="base"
          />
        </div>
      </section>

      <nav className="inv-tabs" aria-label="Rings">
        {rings.rings.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={r.id === ringId}
            onClick={() => onRing(r.id)}
          >
            <strong>{r.label}</strong>
            <span>
              {r.n_ads} ads · {r.n_phones} numbers
            </span>
            <span>
              {r.first_seen} to {r.last_seen}
            </span>
          </button>
        ))}
      </nav>

      {ring ? (
        <>
          <div className="inv-grid">
            <RingGraph data={ring} selected={selected} onPick={onPick} />
            <aside className="inv-side" aria-live="polite">
              {pickedAd ? (
                <div className="inv-ad">
                  <h3>
                    Ad {pickedAd.id} <small>{pickedAd.posted_at}</small>
                  </h3>
                  <p className="inv-sub">
                    {pickedAd.hood} · ${pickedAd.rent}/month · <code>{pickedAd.phone}</code>
                  </p>
                  <p>{pickedAd.text}</p>
                  <code className="inv-photos">{pickedAd.photos.join(" ")}</code>
                </div>
              ) : (
                <p className="inv-sub">
                  Select an ad in the graph, the strip or any evidence list to read it.
                </p>
              )}
              {ring.ring.sources.length ? (
                <p className="inv-sub">
                  Photos in this ring were first posted in honest ads {ring.ring.sources.join(", ")}
                  . Those ads are sources of the copies, not members of the ring.
                </p>
              ) : null}
            </aside>
          </div>
          <TimelineStrip data={ring} selected={selected} onPick={onPick} />
          <section className="inv-findings" aria-label="Findings">
            <h2>What links these ads</h2>
            <div className="inv-finding-list">
              {ring.ring.findings.map((f) => (
                <FindingCard key={f.id} finding={f} onPick={onPick} />
              ))}
            </div>
          </section>
        </>
      ) : (
        <p className="inv-sub">Loading the ring.</p>
      )}

      <AskPanel examples={rings.example_questions} onPick={onPick} ask={ask} />
      <footer className="inv-foot">
        SYNTHETIC DATA. Every ad, number and photo id in this view was generated for the demo.
        Nothing is real, and nothing comes from CoStar, Matterport or Vexcel.
      </footer>
    </div>
  );
}

export function InvestigatePage() {
  const [rings, setRings] = useState<RingsResponse | null>(null);
  const [ringId, setRingId] = useState("A");
  const [ring, setRing] = useState<RingResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getJson<RingsResponse>("/forensics/rings")
      .then((r) => {
        setRings(r);
        if (r.rings[0]) setRingId(r.rings[0].id);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!rings) return;
    let live = true;
    setRing(null);
    getJson<RingResponse>(`/forensics/rings/${ringId}`)
      .then((r) => {
        if (live) setRing(r);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [rings, ringId]);

  if (failed) {
    return (
      <div className="inv-page">
        <p className="inv-error">
          The investigator view needs the API (make api). It could not be reached.
        </p>
      </div>
    );
  }
  if (!rings) {
    return (
      <div className="inv-page">
        <p className="inv-sub">Loading the case.</p>
      </div>
    );
  }
  return (
    <InvestigateView
      rings={rings}
      ring={ring}
      ringId={ringId}
      onRing={(id) => {
        setRingId(id);
        setSelected(null);
      }}
      selected={selected}
      onPick={setSelected}
      ask={async (question) => {
        const res = await fetch(`${base()}/forensics/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        return (await res.json()) as Answer;
      }}
    />
  );
}

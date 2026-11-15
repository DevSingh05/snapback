import { useEffect, useState } from "react";

import { apiBase } from "../api";
import type { CaseFile, CaseLink, CaseStudy, StudyStep, TieKind } from "./types";
import "./casefile.css";

function base(): string {
  return apiBase() ?? "/api";
}

export async function fetchCaseFile(id: string): Promise<CaseFile> {
  const res = await fetch(`${base()}/forensics/rings/${id}/case-file`);
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as CaseFile;
}

export async function fetchCaseStudy(): Promise<CaseStudy> {
  const res = await fetch(`${base()}/forensics/case-study`);
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as CaseStudy;
}

export const KIND_LABEL: Record<TieKind, string> = {
  phone: "Shared phone",
  photo: "Shared photo hash",
  wording: "Shared wording",
  link: "Shared link",
};

export function money(usd: number | null): string {
  return usd === null ? "not stated" : `$${usd.toLocaleString("en-US")}`;
}

export function exportName(cf: CaseFile): string {
  return `case-file-ring-${cf.ring.id}-SYNTHETIC.json`;
}

export function exportJson(cf: CaseFile): string {
  return JSON.stringify(cf, null, 2);
}

export function gapText(cf: CaseFile): string {
  const d = cf.detection;
  if (d.flagged_on === null || d.days_first_ad_to_flag === null) {
    return "Never flagged by the detector";
  }
  const n = d.days_first_ad_to_flag;
  return `${n} day${n === 1 ? "" : "s"} from the first ad to the flag`;
}

/** What one link rests on, in words an investigator can check against the ads. */
export function evidenceText(link: CaseLink): string {
  const e = link.evidence;
  if (link.kind === "phone") return `same number ${e.phone ?? ""}`;
  if (link.kind === "photo") {
    return `${e.photo_sets ?? 0} photo set(s) reused, closest pair ${e.closest_bits ?? "?"} of 64 bits apart${
      e.strong ? "" : " (one picture only)"
    }`;
  }
  if (link.kind === "wording") return `“${e.span_older ?? ""}” / “${e.span_newer ?? ""}”`;
  return `site ${(e.hosts ?? []).join(", ")}`;
}

function download(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function CaseFileBody({ cf, onPick }: { cf: CaseFile; onPick?: (adId: number) => void }) {
  const linksByAd = new Map<number, CaseLink[]>();
  for (const lk of cf.links) linksByAd.set(lk.to_ad, [...(linksByAd.get(lk.to_ad) ?? []), lk]);
  const d = cf.detection;
  const strongest = cf.signals.filter((s) => cf.strongest.includes(s.kind));
  return (
    <div className="cf-body">
      <section className="cf-facts" aria-label="Detection">
        <div>
          <span className="cf-k">First ad</span>
          <strong>{d.first_ad_date}</strong>
          <small>ad {d.first_ad_id}</small>
        </div>
        <div>
          <span className="cf-k">Flagged</span>
          <strong>{d.flagged_on ?? "never"}</strong>
          <small>{d.flag_ad_id ? `when ad ${d.flag_ad_id} was posted` : "no flag"}</small>
        </div>
        <div>
          <span className="cf-k">First ad to flag</span>
          <strong>
            {d.days_first_ad_to_flag === null ? "n/a" : `${d.days_first_ad_to_flag} days`}
          </strong>
          <small>{d.ads_up_before_flag} ads were up before the flag</small>
        </div>
        <div>
          <span className="cf-k">Strongest signals</span>
          <strong>{strongest.map((s) => s.label).join(" + ") || "none"}</strong>
          <small>by link count times the finder&apos;s weight</small>
        </div>
      </section>
      <p className="cf-method">{d.method}</p>

      <h3>Every ad, in posting order</h3>
      <ol className="cf-timeline">
        {cf.timeline.map((ad) => (
          <li key={ad.id}>
            <button type="button" className="cf-adbtn" onClick={() => onPick?.(ad.id)}>
              <time>{ad.posted_at}</time> ad {ad.id}
            </button>
            <span className="cf-meta">
              <code>{ad.phone}</code> · {ad.hood} · ${ad.rent}/month · asks:{" "}
              {ad.amount_asked.item ?? "no ask found"} ({money(ad.amount_asked.usd)})
            </span>
            <ul className="cf-ties">
              {(linksByAd.get(ad.id) ?? []).length === 0 ? (
                <li className="cf-none">
                  {ad.id === d.first_ad_id
                    ? "First ad of the ring."
                    : "No direct tie to an earlier ad."}
                </li>
              ) : (
                (linksByAd.get(ad.id) ?? []).map((lk) => (
                  <li key={`${lk.kind}-${lk.from_ad}`} data-kind={lk.kind}>
                    <b>{KIND_LABEL[lk.kind]}</b> with ad {lk.from_ad}: {evidenceText(lk)}
                  </li>
                ))
              )}
            </ul>
          </li>
        ))}
      </ol>

      <h3>Signals, strongest first</h3>
      <table className="cf-table">
        <thead>
          <tr>
            <th>Signal</th>
            <th>Links</th>
            <th>Weight</th>
            <th>Strength</th>
          </tr>
        </thead>
        <tbody>
          {[...cf.signals]
            .sort((a, b) => b.strength - a.strength)
            .map((s) => (
              <tr key={s.kind}>
                <td>{s.label}</td>
                <td>{s.n_links}</td>
                <td>{s.weight}</td>
                <td>{s.strength}</td>
              </tr>
            ))}
        </tbody>
      </table>

      <h3>What is not known</h3>
      <ul className="cf-unknown">
        {cf.not_known.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

export function CaseFilePanel({
  ringId,
  onPick,
  load = fetchCaseFile,
}: {
  ringId: string;
  onPick?: (adId: number) => void;
  load?: (id: string) => Promise<CaseFile>;
}) {
  const [cf, setCf] = useState<CaseFile | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    setCf(null);
    setFailed(false);
    load(ringId)
      .then((v) => live && setCf(v))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [ringId, load]);
  if (failed) return <p className="inv-error">The case file could not be built.</p>;
  if (!cf)
    return (
      <p className="inv-sub" role="status">
        Building the case file. The detector is replayed day by day, so this takes a few seconds.
      </p>
    );
  return (
    <section className="cf-panel" aria-label={`Case file, ${cf.ring.label}`}>
      <header className="cf-head">
        <div>
          <p className="inv-eyebrow">Case file</p>
          <h2>
            {cf.ring.label}: {cf.ring.n_ads} ads, {cf.ring.n_phones} numbers
          </h2>
          <p className="inv-sub">{gapText(cf)}.</p>
        </div>
        <div className="cf-actions">
          <span className="inv-chip inv-chip-synth">SYNTHETIC DATA</span>
          <button type="button" onClick={() => download(exportName(cf), exportJson(cf))}>
            Export JSON
          </button>
          <a href={`/investigate/case/${cf.ring.id}`} target="_blank" rel="noreferrer">
            Printable attachment
          </a>
        </div>
      </header>
      <CaseFileBody cf={cf} onPick={onPick} />
    </section>
  );
}

// ---- the printable attachment ------------------------------------------------------------

export function CaseAttachment({ cf }: { cf: CaseFile }) {
  const d = cf.detection;
  return (
    <article className="cf-print">
      <header>
        <p className="cf-print-synth">
          SYNTHETIC DATA. Every ad, number and name below was generated. Nothing is real.
        </p>
        <h1>Attachment: pattern of related rental ads</h1>
        <p>
          Laid out as a supporting attachment for a fraud report (FTC ReportFraud, FBI IC3). It is
          not an official form. Reference: {cf.ring.label}, schema {cf.schema}.
        </p>
      </header>

      <h2>1. Summary</h2>
      <dl className="cf-dl">
        <dt>Ads in the pattern</dt>
        <dd>{cf.ring.n_ads}</dd>
        <dt>Contact numbers</dt>
        <dd>{cf.ring.n_phones}</dd>
        <dt>First ad</dt>
        <dd>
          {d.first_ad_date} (ad {d.first_ad_id})
        </dd>
        <dt>Flagged by the detector</dt>
        <dd>
          {d.flagged_on ?? "never"}
          {d.days_first_ad_to_flag !== null
            ? `, ${d.days_first_ad_to_flag} days after the first ad`
            : ""}
        </dd>
        <dt>Strongest signals</dt>
        <dd>{cf.strongest.map((k) => KIND_LABEL[k]).join(", ") || "none"}</dd>
      </dl>

      <h2>2. The ads</h2>
      <table className="cf-table">
        <thead>
          <tr>
            <th>Ad</th>
            <th>Date posted</th>
            <th>Contact</th>
            <th>Location</th>
            <th>Rent listed</th>
            <th>Amount asked up front</th>
            <th>Ask, as worded</th>
          </tr>
        </thead>
        <tbody>
          {cf.timeline.map((ad) => (
            <tr key={ad.id}>
              <td>{ad.id}</td>
              <td>{ad.posted_at}</td>
              <td>{ad.phone}</td>
              <td>{ad.hood}</td>
              <td>${ad.rent}</td>
              <td>
                {ad.amount_asked.item ?? "none found"}: {money(ad.amount_asked.usd)}
                {ad.amount_asked.usd === null ? null : <small> ({ad.amount_asked.basis})</small>}
              </td>
              <td>{ad.amount_asked.sentence ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>3. Contact identifiers</h2>
      <table className="cf-table">
        <thead>
          <tr>
            <th>Phone</th>
            <th>Used in ads</th>
          </tr>
        </thead>
        <tbody>
          {cf.contacts.map((c) => (
            <tr key={c.phone}>
              <td>{c.phone}</td>
              <td>{c.ad_ids.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>4. Links between ads</h2>
      <table className="cf-table">
        <thead>
          <tr>
            <th>Earlier ad</th>
            <th>Later ad</th>
            <th>Signal</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {cf.links.map((lk) => (
            <tr key={`${lk.kind}-${lk.from_ad}-${lk.to_ad}`}>
              <td>{lk.from_ad}</td>
              <td>{lk.to_ad}</td>
              <td>{KIND_LABEL[lk.kind]}</td>
              <td>{evidenceText(lk)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>5. Not known</h2>
      <ul>
        {cf.not_known.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <p className="cf-print-foot">
        {cf.detection.method} A link shows two ads share something. It does not show who posted
        them.
      </p>
    </article>
  );
}

export function CaseAttachmentPage({ ringId }: { ringId: string }) {
  const [cf, setCf] = useState<CaseFile | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetchCaseFile(ringId)
      .then(setCf)
      .catch(() => setFailed(true));
  }, [ringId]);
  if (failed)
    return (
      <p className="inv-error">
        The full case file runs on our demo laptop (live API). This public site shows the sample
        rings.
      </p>
    );
  if (!cf) return <p className="inv-sub">Building the case file.</p>;
  return (
    <div className="cf-print-page">
      <div className="cf-print-bar">
        <button type="button" onClick={() => window.print()}>
          Print or save as PDF
        </button>
        <button type="button" onClick={() => download(exportName(cf), exportJson(cf))}>
          Export JSON
        </button>
      </div>
      <CaseAttachment cf={cf} />
    </div>
  );
}

// ---- the case study ----------------------------------------------------------------------

function StepCard({ step }: { step: StudyStep }) {
  return (
    <li className="cs-step" data-flagged={step.flagged}>
      <div className="cs-day">
        <span>Day</span>
        <strong>{step.day_no}</strong>
        <time>{step.date}</time>
      </div>
      <div className="cs-what">
        {step.lines.map((l) => (
          <p key={l}>{l}</p>
        ))}
        <p className="cs-detector">{step.detector}</p>
        {step.ties.length ? (
          <div className="cs-chips">
            {step.ties.map((t) => (
              <span
                key={`${t.kind}-${t.from_ad}-${t.to_ad}`}
                className="cs-chip"
                data-kind={t.kind}
              >
                {KIND_LABEL[t.kind]}: ad {t.from_ad} to ad {t.to_ad}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function CaseStudyView({ load = fetchCaseStudy }: { load?: () => Promise<CaseStudy> }) {
  const [cs, setCs] = useState<CaseStudy | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    load()
      .then((v) => live && setCs(v))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [load]);
  if (failed)
    return (
      <p className="inv-error">
        The full case study runs on our demo laptop (live API). This public site shows the sample
        rings.
      </p>
    );
  if (!cs)
    return (
      <p className="inv-sub" role="status">
        Replaying the detector day by day. This takes a few seconds.
      </p>
    );
  return (
    <section className="cs" aria-label="Case study">
      <header className="cf-head">
        <div>
          <p className="inv-eyebrow">Case study · {cs.ring.label}</p>
          <h2>From the first ad to the flag</h2>
          <p className="inv-sub">
            Every step below is the ring finder run on only the ads posted up to that day. The
            sentences are built from what it found, not written by hand.
          </p>
        </div>
        <span className="inv-chip inv-chip-synth">SYNTHETIC DATA</span>
      </header>
      <ol className="cs-steps">
        {cs.steps.map((s) => (
          <StepCard key={s.step} step={s} />
        ))}
      </ol>
      <p className="cs-after">
        {cs.days_first_ad_to_flag !== null
          ? `Flagged ${cs.days_first_ad_to_flag} days after the first ad. `
          : ""}
        {cs.after.text}
      </p>
      <h3>What is still not known</h3>
      <ul className="cf-unknown">
        {cs.not_known.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </section>
  );
}

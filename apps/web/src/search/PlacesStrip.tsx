import { useEffect, useState } from "react";

import { HouseGlyph } from "../components/HouseGlyph";
import { SourceChip } from "../components/SourceChip";
import type { PlaceMatch, RenterBrief, TourDraft } from "../contracts";
import {
  briefIsEmpty,
  NoReadToken,
  fetchAlternatives,
  requestTourDraft,
  searchPlaces,
  type Places,
} from "./api";
import "./search.css";

type Load =
  | { status: "loading" }
  | { status: "ready"; places: Places }
  | { status: "error"; message: string; retry: boolean };

type DraftState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; draft: TourDraft }
  | { status: "error"; message: string };

interface Props {
  // The checked ad's case. Without one there is no write token, so drafting is not offered.
  caseId: string | null;
  brief: RenterBrief | null;
  heading?: string;
}

// The tour-prep pack for a researched place. The plan is picked by its key, never its label.
function prepHref(place: PlaceMatch): string {
  const q = place.plan_key ? `?plan_key=${encodeURIComponent(place.plan_key)}` : "";
  return `/prep/place/${encodeURIComponent(place.property_id)}${q}`;
}

const SCAN_LABEL = "a 3D scan in this building";

function PlaceRow({
  place,
  caseId,
  brief,
}: {
  place: PlaceMatch;
  caseId: string | null;
  brief: RenterBrief | null;
}) {
  const [draft, setDraft] = useState<DraftState>({ status: "idle" });
  const [copied, setCopied] = useState(false);
  const title = place.floor_plan ?? (place.kind === "house" ? "House" : "Apartment");

  async function ask() {
    if (!caseId) return;
    setDraft({ status: "loading" });
    setCopied(false);
    try {
      setDraft({ status: "ready", draft: await requestTourDraft(caseId, place, brief) });
    } catch (err) {
      setDraft({
        status: "error",
        message: err instanceof Error ? err.message : "Something went wrong. Try again.",
      });
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <li className="pf-row" data-testid="place-row" data-fit={place.budget_fit}>
      <div className="pf-row-head">
        <h3 className="pf-row-title">{title}</h3>
        <SourceChip source={place.source} />
      </div>
      <p className="pf-price">{place.price_text}</p>
      <p className="pf-avail">{place.availability_text}</p>
      {place.must_haves.length > 0 && (
        <ul className="pf-musts" aria-label="Your must-haves">
          {place.must_haves.map((m) => (
            <li key={m.key} data-met={m.met === true ? "yes" : m.met === false ? "no" : "unknown"}>
              {m.text}
            </li>
          ))}
        </ul>
      )}
      {place.has_3d_scan && <p className="pf-scan">{place.scan_text ?? SCAN_LABEL}</p>}
      {place.office_on_record && (
        <p className="pf-office">
          Leasing office on record: <strong>{place.office_on_record}</strong>
        </p>
      )}

      <a className="pf-action pf-link" href={prepHref(place)} data-testid="tour-prep-link">
        Tour prep
      </a>
      {caseId && place.office_on_record && draft.status !== "ready" && (
        <button
          type="button"
          className="pf-action"
          disabled={draft.status === "loading"}
          onClick={() => void ask()}
        >
          {draft.status === "loading" ? "Drafting…" : "Draft a tour request"}
        </button>
      )}
      {draft.status === "error" && (
        <p className="pf-error" role="alert">
          {draft.message}
        </p>
      )}
      {draft.status === "ready" && (
        <section className="pf-draft">
          <p className="pf-draft-to">
            To: <strong>{draft.draft.addressee}</strong>
          </p>
          <label htmlFor={`draft-${place.property_id}-${place.plan_key ?? ""}`} className="sr-only">
            Tour request draft
          </label>
          <textarea
            id={`draft-${place.property_id}-${place.plan_key ?? ""}`}
            className="pf-draft-text"
            rows={6}
            readOnly
            value={draft.draft.text}
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="pf-draft-actions">
            <button type="button" className="pf-action" onClick={() => void copy(draft.draft.text)}>
              Copy
            </button>
            <span role="status" className="pf-note">
              {copied ? "Copied." : ""}
            </span>
          </div>
          <p className="pf-note">We never send it for you. You copy it and send it yourself.</p>
        </section>
      )}
    </li>
  );
}

export function PlacesStrip({ caseId, brief, heading }: Props) {
  const title =
    heading ??
    (briefIsEmpty(brief)
      ? "Researched places near this price"
      : "Researched places that fit your budget");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const briefKey = JSON.stringify(brief);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoad({ status: "loading" });
    const run =
      !briefIsEmpty(brief) || !caseId
        ? searchPlaces(brief ?? {}, ctrl.signal)
        : fetchAlternatives(caseId, ctrl.signal);
    run
      .then((places) => setLoad({ status: "ready", places }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setLoad({
          status: "error",
          message: err instanceof Error ? err.message : "Something went wrong. Try again.",
          retry: !(err instanceof NoReadToken),
        });
      });
    return () => ctrl.abort();
    // briefKey is the stable form of brief
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, briefKey, attempt]);

  return (
    <section className="pf-strip" aria-labelledby="pf-strip-title" data-testid="places-strip">
      <div className="pf-strip-head">
        <h2 id="pf-strip-title">{title}</h2>
        {load.status === "ready" && <SourceChip source={load.places.source} />}
      </div>
      {load.status === "ready" && <p className="pf-asof">{load.places.as_of}</p>}

      {load.status === "loading" && <p className="pf-note">Looking up researched places…</p>}
      {load.status === "error" && (
        <div className="pf-empty" role="alert">
          <p>We could not load places right now.</p>
          <p className="pf-note">{load.message}</p>
          {load.retry && (
            <button type="button" className="pf-action" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          )}
        </div>
      )}
      {load.status === "ready" && load.places.matches.length === 0 && (
        <div className="pf-empty" data-testid="places-empty">
          <HouseGlyph className="pf-empty-house" lit={false} />
          <p>No researched places fit this budget and these must-haves.</p>
          {load.places.tradeoff_question && (
            <p className="pf-tradeoff">{load.places.tradeoff_question}</p>
          )}
        </div>
      )}
      {load.status === "ready" && load.places.matches.length > 0 && (
        <ul className="pf-rows">
          {load.places.matches.map((p) => (
            <PlaceRow
              key={`${p.property_id}-${p.plan_key ?? p.floor_plan ?? ""}`}
              place={p}
              caseId={caseId}
              brief={brief}
            />
          ))}
        </ul>
      )}
      {load.status === "ready" && !caseId && load.places.matches.length > 0 && (
        <p className="pf-note">To draft a tour request, paste an ad above and check it first.</p>
      )}
    </section>
  );
}

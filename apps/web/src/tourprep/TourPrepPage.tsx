import { Fragment, useEffect, useState } from "react";

import { Wordmark } from "../components/HouseGlyph";
import { KitArt } from "../components/KitArt";
import { SourceChip } from "../components/SourceChip";
import type { TourPrepPack } from "../contracts";
import { fetchPack, packToText, PackNeedsToken, type Lang, type PackTarget } from "./api";
import "./tourprep.css";

type Load =
  | { status: "loading" }
  | { status: "ready"; pack: TourPrepPack }
  | { status: "error"; message: string };

export function TourPrepPage({ target, back }: { target: PackTarget; back: string }) {
  // The demo path is English only: Spanish, and its toggle, appear only with ?lang=es.
  const [spanishAsked] = useState(
    () => new URLSearchParams(window.location.search).get("lang") === "es",
  );
  const [lang, setLang] = useState<Lang>(spanishAsked ? "es" : "en");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [copied, setCopied] = useState(false);
  const targetKey = JSON.stringify(target);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoad({ status: "loading" });
    setCopied(false);
    fetchPack(target, lang, ctrl.signal)
      .then((pack) => setLoad({ status: "ready", pack }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setLoad({
          status: "error",
          message:
            err instanceof PackNeedsToken
              ? "Open this from the device that checked the ad: its result key is not here."
              : err instanceof Error
                ? err.message
                : "Something went wrong. Try again.",
        });
      });
    return () => ctrl.abort();
    // targetKey is the stable form of target
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetKey, lang, attempt]);

  async function copy(pack: TourPrepPack) {
    try {
      await navigator.clipboard.writeText(packToText(pack));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="tp-page" data-testid="tour-prep">
      <nav className="tp-bar no-print" aria-label="Tour prep tools">
        <a className="tp-back" href={back}>
          Back
        </a>
        {spanishAsked && (
          <div className="tp-lang" role="group" aria-label="Language">
            {(["en", "es"] as const).map((l) => (
              <button
                key={l}
                type="button"
                className="tp-lang-btn"
                aria-pressed={lang === l}
                onClick={() => setLang(l)}
              >
                {l === "en" ? "English" : "Español"}
              </button>
            ))}
          </div>
        )}
        {load.status === "ready" && (
          <div className="tp-tools">
            <button type="button" className="pf-action" onClick={() => void copy(load.pack)}>
              {lang === "es" ? "Copiar" : "Copy"}
            </button>
            <button type="button" className="pf-action" onClick={() => window.print()}>
              {lang === "es" ? "Imprimir" : "Print"}
            </button>
            <span role="status" className="pf-note">
              {copied ? (lang === "es" ? "Copiado." : "Copied.") : ""}
            </span>
          </div>
        )}
      </nav>

      {load.status === "loading" && (
        <p className="pf-note wait" role="status">
          Loading…
        </p>
      )}
      {load.status === "error" && (
        <div className="pf-empty" role="alert">
          <KitArt kind="house" className="pf-empty-house" lit={false} />
          <p>We could not load the tour prep.</p>
          <p className="pf-note">{load.message}</p>
          <button type="button" className="pf-action" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      )}
      {load.status === "ready" && <Pack pack={load.pack} />}
    </article>
  );
}

function Pack({ pack }: { pack: TourPrepPack }) {
  return (
    <div className="tp-sheet" lang={pack.lang}>
      <div className="tp-mast">
        <Wordmark />
        <SourceChip source={pack.source} />
      </div>
      <header className="tp-head">
        <div>
          <h1>{pack.title}</h1>
          <p className="tp-sub">{pack.subtitle}</p>
        </div>
        <KitArt kind="prep" className="tp-art" />
      </header>

      <section aria-labelledby="tp-facts">
        <h2 id="tp-facts">{pack.facts_heading}</h2>
        {pack.facts.length === 0 ? null : (
          <ul className="tp-list" data-testid="tp-facts">
            {pack.facts.map((f) => (
              <li key={f.key}>
                <p className="tp-text">{f.text}</p>
                <p className="tp-src">
                  {f.sources.map((src, i) => (
                    <Fragment key={src}>
                      {i > 0 ? " · " : null}
                      <span className="prov">{src}</span>
                    </Fragment>
                  ))}
                  {f.as_of ? (
                    <>
                      {f.sources.length > 0 ? " · " : null}
                      {f.as_of}
                    </>
                  ) : null}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="tp-ask">
        <h2 id="tp-ask">{pack.questions_heading}</h2>
        <ol className="tp-list tp-num" data-testid="tp-questions">
          {pack.questions.map((q) => (
            <li key={q.key}>
              <p className="tp-text">{q.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="tp-pay" className="tp-pay">
        <h2 id="tp-pay">{pack.pay_heading}</h2>
        <ol className="tp-list tp-num" data-testid="tp-pay">
          {pack.before_you_pay.map((s) => (
            <li key={s}>
              <p className="tp-text">{s}</p>
            </li>
          ))}
        </ol>
      </section>

      <p className="tp-note">{pack.note}</p>
    </div>
  );
}

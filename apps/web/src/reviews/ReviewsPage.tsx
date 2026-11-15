import { RealtorQuote } from "../landing/RealtorQuote";
import data from "./reviews.json";
import { publicQuotes, summarize, type ReviewsFile } from "./summary";
import "./reviews.css";

// /reviews: what people who tried SNAPBACK said, counted from a static file the team refreshes
// before each deploy. Every response is in the numbers; only reviewers who wrote a quote for us
// to share appear in the quotes.

const RATE_URL = "https://forms.gle/rDczNc1TT1EAJcw6A";

const fmt = (v: number | null) => (v === null ? "n/a" : v.toFixed(1));

export function ReviewsPage({ file = data as ReviewsFile }: { file?: ReviewsFile } = {}) {
  const s = summarize(file.responses);
  const quotes = publicQuotes(file.responses);
  const formUrl = file.form_url.trim();
  const n = `n = ${s.n}`;
  const button = formUrl ? (
    <a className="ui-btn-quiet rv-cta" href={formUrl} target="_blank" rel="noreferrer">
      Leave a review
    </a>
  ) : null;

  return (
    <div className="rv" data-testid="reviews">
      <h1 className="rv-title">Reviews</h1>
      {s.n === 0 ? (
        <section className="rv-empty" data-testid="reviews-empty">
          <RealtorQuote lang="en" />
          <p className="rv-empty-line">Hallway test tonight: results posted after 08:30 with n</p>
          <a
            className="ui-btn-quiet rv-cta"
            href={formUrl || RATE_URL}
            target="_blank"
            rel="noreferrer"
          >
            Rate SNAPBACK (2 minutes)
          </a>
        </section>
      ) : (
        <>
          <section aria-labelledby="rv-sum" className="rv-sum">
            <h2 id="rv-sum" className="rv-h2">
              {s.n} {s.n === 1 ? "review" : "reviews"}
            </h2>
            <dl className="rv-stats">
              <div className="rv-stat">
                <dt>Easy to understand</dt>
                <dd>
                  {fmt(s.avgEasy)} <span>out of 5</span>
                </dd>
                <p>{n}</p>
              </div>
              <div className="rv-stat">
                <dt>Trust before paying</dt>
                <dd>
                  {fmt(s.avgTrust)} <span>out of 5</span>
                </dd>
                <p>{n}</p>
              </div>
              <div className="rv-stat">
                <dt>Would use it again</dt>
                <dd>{s.useAgainPct}%</dd>
                <p>{n}</p>
              </div>
              <div className="rv-stat">
                <dt>Would NOT pay a deposit on the sample ad</dt>
                <dd>{s.wouldNotPayPct}%</dd>
                <p>{n}</p>
              </div>
            </dl>
          </section>
          {quotes.length > 0 && (
            <section aria-labelledby="rv-q" className="rv-quotes">
              <h2 id="rv-q" className="rv-h2">
                In their words
              </h2>
              <ul>
                {quotes.map((q, i) => (
                  <li key={i}>
                    <blockquote>
                      <p>{q.quote}</p>
                      <footer>{q.by}</footer>
                    </blockquote>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {button}
        </>
      )}
      <p className="rv-note">
        Every response is counted here, good or bad. Quotes appear only when the reviewer wrote one
        for us to share.
      </p>
      {file.updated && <p className="rv-note">Updated {file.updated}</p>}
    </div>
  );
}

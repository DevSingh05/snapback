import { useEffect, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import { answerOffice, peekOffice, type OfficePeek } from "./api";
import "./office.css";

// The page an office opens from the one-time link: /confirm#<token>. The token is in the
// fragment, which a browser never sends to a server, and is taken out of the address bar as soon
// as it is read. Looking changes nothing; only a button press answers.
export function ConfirmPage() {
  const [token] = useState(() => window.location.hash.replace(/^#/, ""));
  const [seen, setSeen] = useState<OfficePeek | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      setError("This link is missing its code. Open the link from the email again.");
      return;
    }
    peekOffice(token)
      .then(setSeen)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [token]);

  const answer = async (decision: "yes" | "no") => {
    setBusy(true);
    try {
      setDone((await answerOffice(token, decision)).message);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const ad = seen?.listing;
  const contacts = ad ? [...ad.phones, ...ad.emails, ...ad.links] : [];
  return (
    <div className="of-panel" data-testid="confirm-page">
      <span className="wordmark">SNAPBACK</span>
      {done ? (
        <p role="status" data-testid="confirm-done">
          {done}
        </p>
      ) : error ? (
        <p role="alert" data-testid="confirm-error">
          {error}
        </p>
      ) : !seen || !ad ? (
        <p>Loading…</p>
      ) : (
        <>
          <div className="of-head">
            <h1>Is this ad yours?</h1>
            <SourceChip source={seen.source} />
          </div>
          <p>
            Someone asked SNAPBACK to check a rental ad for a property whose website on record is{" "}
            <strong>{seen.domain}</strong>. Nothing changes until you press a button.
          </p>
          <dl className="of-ad" data-testid="confirm-ad">
            {ad.building || ad.address ? (
              <>
                <dt>Property on record</dt>
                <dd>{[ad.building, ad.address].filter(Boolean).join(", ")}</dd>
              </>
            ) : null}
            {ad.unit ? (
              <>
                <dt>Unit in the ad</dt>
                <dd>{ad.unit}</dd>
              </>
            ) : null}
            {ad.rent ? (
              <>
                <dt>Rent in the ad</dt>
                <dd>${ad.rent.toLocaleString("en-US")} a month</dd>
              </>
            ) : null}
            <dt>Posted by</dt>
            <dd>{ad.poster ?? "The ad names no company"}</dd>
            {contacts.length > 0 ? (
              <>
                <dt>Contacts in the ad</dt>
                <dd>{contacts.join(", ")}</dd>
              </>
            ) : null}
          </dl>
          <p>
            Is this ad, posted by {ad.poster ?? "this poster"}
            {contacts[0] ? ` / ${contacts[0]}` : ""}, yours?
          </p>
          <div className="of-buttons">
            <button type="button" disabled={busy} onClick={() => answer("yes")}>
              Yes, ours
            </button>
            <button type="button" disabled={busy} onClick={() => answer("no")}>
              Not ours
            </button>
          </div>
        </>
      )}
    </div>
  );
}

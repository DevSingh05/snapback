import { useEffect, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import { fetchOffice, requestOfficeLink, type OfficeStatus } from "./api";
import "./office.css";

// "Ask the office to confirm": shows the website domain CoStar has on record for the office, and
// takes the address the poster gave the renter. A link goes to that address only if it is at that
// domain. In this demo the link lands in a local outbox file; nothing is sent.
export function OfficeConfirm({ caseId, onChanged }: { caseId: string; onChanged?: () => void }) {
  const [status, setStatus] = useState<OfficeStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetchOffice(caseId)
      .then(setStatus)
      .catch(() => setStatus(null));
  };
  useEffect(load, [caseId]);

  if (!status) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sent = await requestOfficeLink(caseId, address.trim());
      setMessage(`${sent.detail} It works once and lasts ${sent.expires_in_minutes} minutes.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="of-panel" aria-labelledby="of-title" data-testid="office-confirm">
      <div className="of-head">
        <h2 id="of-title">Ask the office to confirm</h2>
        <SourceChip source={status.source} />
      </div>
      {status.declined ? (
        <p data-testid="office-declined">
          Someone at {status.declined_domain}, the website CoStar has on record for this office,
          said the office does not recognise this ad. A later confirmation does not undo that.
        </p>
      ) : null}
      {status.confirmed ? (
        <p data-testid="office-confirmed">
          Confirmed through {status.confirmed_domain}, the website CoStar has on record for this
          office.
        </p>
      ) : !status.offered || !status.domain ? (
        <p data-testid="office-guidance">{status.guidance}</p>
      ) : (
        <>
          <p>
            CoStar has <strong data-testid="office-domain">{status.domain}</strong> on record as
            this office&apos;s website. Someone with an address there can confirm this listing.
          </p>
          {!open ? (
            <button type="button" onClick={() => setOpen(true)}>
              Ask the office to confirm
            </button>
          ) : (
            <form onSubmit={submit} className="of-form">
              <label className="pf-field">
                The email address the poster gave you (must end in @{status.domain})
                <input
                  type="email"
                  autoComplete="off"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                />
              </label>
              <p className="pf-note">
                A one-time link goes to that address. In this demo it lands in a local outbox file
                on the server; nothing is sent to a real inbox.
              </p>
              <button type="submit" disabled={busy || address.trim() === ""}>
                Make the link
              </button>
            </form>
          )}
          {message ? (
            <p role="status" data-testid="office-sent">
              {message}
            </p>
          ) : null}
          {error ? (
            <p role="alert" data-testid="office-error">
              {error}
            </p>
          ) : null}
          {message ? (
            <button
              type="button"
              onClick={() => {
                load();
                onChanged?.();
              }}
            >
              Check again
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

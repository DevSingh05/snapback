// "What to do next", for a result that did not pass: hold the money, reach the office on record
// through its own website, tell that office with a draft note, and file the report. The note is
// GET /cases/{id}/copy-alert and the pack is GET /cases/{id}/report, both in the API's words.
// Nothing here is ever sent for the renter: the note is a draft to copy, and it is shown only
// when the API says it fires. No phone digits appear, and no line is about a person.
import { useState } from "react";

import "../ui/ui.css";
import "./case.css";
import type { CopyAlert, ReportPack } from "../contracts";
import { Tag } from "../ui";
import { hostLink, withoutPhoneDigits } from "./model";

/** Where to tell the authorities, as plain text with a link each. */
export const AGENCIES = [
  {
    name: "The Federal Trade Commission (FTC)",
    host: "reportfraud.ftc.gov",
    href: "https://reportfraud.ftc.gov/",
  },
  {
    name: "The FBI's Internet Crime Complaint Center (IC3)",
    host: "ic3.gov",
    href: "https://www.ic3.gov/",
  },
] as const;

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ text, label, testId }: { text: string; label: string; testId: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <p className="case-copy">
      <button
        type="button"
        className="ui-btn-quiet"
        data-testid={testId}
        onClick={async () => setState((await copyText(text)) ? "copied" : "failed")}
      >
        {label}
      </button>
      <span role="status" className="case-copy-said">
        {state === "copied"
          ? "Copied. Nothing was sent."
          : state === "failed"
            ? "Could not copy here. Select the text and copy it."
            : ""}
      </span>
    </p>
  );
}

/** The draft note for the leasing office on record. Shown as a draft; the renter sends it. */
export function AlertDraft({ alert }: { alert: CopyAlert }) {
  if (!alert.fires || !alert.draft_body) return null;
  const subject = alert.draft_subject ? withoutPhoneDigits(alert.draft_subject) : null;
  const body = withoutPhoneDigits(alert.draft_body);
  const site = hostLink(alert.website_host);
  return (
    <div className="case-alert" data-testid="case-alert">
      <p className="case-alert-head ui-mono">
        <span>DRAFT · NOT SENT</span>
        <Tag source={alert.source} testId="alert-source" />
      </p>
      {subject ? <p className="case-alert-subject">{subject}</p> : null}
      <div className="case-alert-body" data-testid="alert-body">
        {body.split(/\n{2,}/).map((para) => (
          <p key={para}>{para}</p>
        ))}
      </div>
      <CopyButton
        text={subject ? `${subject}\n\n${body}` : body}
        label="Copy the note"
        testId="alert-copy"
      />
      <p className="case-alert-note">
        SNAPBACK does not send this. Copy it and send it yourself
        {site ? (
          <>
            {" "}
            through the office's own website,{" "}
            <a href={site} target="_blank" rel="noopener noreferrer">
              {alert.website_host}
            </a>
          </>
        ) : (
          " through the office's own website"
        )}
        .
      </p>
    </div>
  );
}

/** The report as plain text, for pasting into a platform's or an agency's form. */
export function reportText(pack: ReportPack, pageUrl: string | null): string {
  const lines = [`SNAPBACK report, case ${pack.case_id}`, "", ...pack.proof_lines];
  if (pageUrl) lines.push("", pageUrl);
  return lines.join("\n");
}

/** "File this report": the pack's own lines and platform steps, then the two agencies. */
export function FilePanel({ pack, pageUrl }: { pack: ReportPack | null; pageUrl: string | null }) {
  const platforms = pack?.reportable ? (pack.platforms ?? []) : [];
  return (
    <div className="case-file" data-testid="case-file">
      {pack && pack.proof_lines.length > 0 ? (
        <div className="case-file-pack" data-testid="file-pack">
          <p className="case-alert-head ui-mono">
            <span>WHAT THIS CHECK FOUND</span>
            <Tag source={pack.source} testId="file-source" />
          </p>
          <ul>
            {pack.proof_lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <CopyButton text={reportText(pack, pageUrl)} label="Copy the report" testId="file-copy" />
        </div>
      ) : null}
      {platforms.length > 0 ? (
        <div className="case-file-where" data-testid="file-platforms">
          <p className="case-file-lead">Report the ad on the site where you found it:</p>
          {platforms.map((p) => (
            <details key={p.platform}>
              <summary>{p.name}</summary>
              <ol>
                {p.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </details>
          ))}
        </div>
      ) : null}
      <div className="case-file-agencies" data-testid="file-agencies">
        <p className="case-file-lead">
          If you sent money, or were pressed to send it, you can also tell:
        </p>
        <ul>
          {AGENCIES.map((a) => (
            <li key={a.host}>
              {a.name}:{" "}
              <a href={a.href} target="_blank" rel="noopener noreferrer">
                {a.host}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function WhatNext({
  alert = null,
  pack = null,
  officeHost = null,
  pageUrl = null,
  id,
  titleId = "case-next-title",
}: {
  alert?: CopyAlert | null;
  pack?: ReportPack | null;
  // The leasing office's own website host, from the record. No phone number is ever shown.
  officeHost?: string | null;
  pageUrl?: string | null;
  id?: string;
  titleId?: string;
}) {
  const site = hostLink(officeHost);
  const draft = alert?.fires && alert.draft_body ? alert : null;
  return (
    <section className="case-todo" id={id} aria-labelledby={titleId} data-testid="case-todo">
      <h2 id={titleId}>What to do next</h2>
      <ol className="case-todo-steps">
        <li data-step="hold">
          <h3>Keep your money for now</h3>
          <p>
            Send no deposit, fee or first month until you have seen the home in person and signed a
            lease.
          </p>
        </li>
        <li data-step="call">
          <h3>Call the leasing office on record</h3>
          <p>
            Use the number on the office's own website, not the one in the ad, and ask if this home
            is theirs to rent.
          </p>
          {site ? (
            <a
              className="case-text-link"
              href={site}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="office-site"
            >
              {officeHost} <span aria-hidden="true">↗</span>
            </a>
          ) : null}
        </li>
        {draft ? (
          <li data-step="tell">
            <h3>Tell the leasing office</h3>
            <p>Here is a note about this ad that you can send them. It is a draft.</p>
            <AlertDraft alert={draft} />
          </li>
        ) : null}
        <li data-step="file">
          <h3>File this report</h3>
          <FilePanel pack={pack} pageUrl={pageUrl} />
        </li>
      </ol>
    </section>
  );
}

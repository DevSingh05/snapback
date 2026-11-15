import "../ui/ui.css";
import {
  LABEL_HINT,
  MERGED,
  nText,
  shownPanels,
  type DataLabel,
  type Measured,
  type Panel,
  type ShowLink,
  type Switches,
} from "./panels";
import "./hood.css";

// /under-the-hood: a map for a judge at the table. One panel per sponsor track: what it does
// for the person, what of theirs we used, what we measured (with n), and a button that opens
// the exact screen where it is working. All of the content lives in panels.ts.

const LABELS: DataLabel[] = ["LIVE", "FIXTURE", "SYNTHETIC"];

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
      <div className="uh-who">
        <span className="uh-mark ui-mono" aria-hidden="true">
          {panel.mark}
        </span>
        <div>
          <h2 id={title} className="uh-sponsor">
            {panel.sponsor}
          </h2>
          <p className="uh-track ui-mono">{panel.track}</p>
        </div>
      </div>
      <div className="uh-what">
        <p className="uh-does">{panel.does}</p>
        <ul className="uh-used" aria-label="What we used">
          {panel.used.map((u) => (
            <li key={u.tech}>
              <strong>{u.tech}</strong>
              <span>{u.text}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="uh-proof ui-on-matte">
        {panel.numbers.length > 0 && (
          <dl className="uh-nums" aria-label="What we measured">
            {panel.numbers.map((m) => (
              <Figure key={m.value + m.what} m={m} />
            ))}
          </dl>
        )}
        {lead && <p className="uh-live">{panel.aside}</p>}
        <div className="uh-go">
          <a className="uh-show" href={panel.show.href}>
            <span>{panel.show.label}</span>
            <span className="uh-arrow" aria-hidden="true">
              →
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
      </div>
    </section>
  );
}

export function HoodPage({ switches = MERGED }: { switches?: Switches } = {}) {
  const panels = shownPanels(switches);
  return (
    <div className="uh" data-testid="hood">
      <header className="uh-head">
        <h1 className="uh-title">Under the hood</h1>
        <p className="uh-lede">
          What SNAPBACK is built on, what we measured, and the exact screen where you can see each
          part working.
        </p>
        <nav className="uh-jump" aria-label="Sponsors">
          {panels.map((p) => (
            <a key={p.id} href={`#${p.id}`}>
              <span className="uh-mark uh-mark-sm ui-mono" aria-hidden="true">
                {p.mark}
              </span>
              {p.sponsor}
            </a>
          ))}
        </nav>
        <ul className="uh-key" aria-label="What the labels mean">
          {LABELS.map((l) => (
            <li key={l}>
              <DataTag label={l} />
              <span>{LABEL_HINT[l]}</span>
            </li>
          ))}
        </ul>
      </header>
      {panels.map((p) => (
        <PanelView key={p.id} panel={p} />
      ))}
      <p className="uh-foot">
        Every figure here was measured by the team, with its n beside it. Nothing from CoStar's
        record is printed on this page.
      </p>
    </div>
  );
}

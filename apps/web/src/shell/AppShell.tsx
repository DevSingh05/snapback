import { useEffect, useRef, useState, type ReactNode } from "react";

import { Lockup } from "../ui/Mark";
import { loadPrefs, savePrefs, TABS, type Prefs, type Section } from "./prefs";
import "./shell.css";

export type { Section };

interface Props {
  /** Which main tab the page belongs to. Null: none (a result, a walk). */
  section: Section | null;
  /** A tab for where you are inside a place, shown only while you are there. */
  context?: { label: string; href: string } | null;
  /** "photo": the bar floats transparent over a photograph at the top of the page (Home,
   *  Stories). A page can also ask for it by carrying `data-bar="photo"` on its hero. */
  bar?: "photo";
  children: ReactNode;
}

/** What each page is for, in one line. One purpose per page. */
export const PURPOSE: Record<string, string> = {
  home: "Ask anything: check an ad, find a place, or open any view.",
  listings: "Browse the researched places.",
  map: "Find a home by where it is.",
  finder: "The agent that learns what you want and helps you find a home.",
  replays: "Real reported cases, replayed step by step.",
  Walk: "See the home, room by room, before you visit.",
  "Tour prep": "Get ready to visit: what to ask and what to check.",
};

/** The website's address, when the app is built knowing it.  */
const SITE_URL = import.meta.env.VITE_SITE_URL as string | undefined;

/** Phones: under this width the tabs sit fixed at the bottom. */
const PHONE = "(max-width: 760px)";

function usePhone(): boolean {
  const [phone, setPhone] = useState(() => window.matchMedia?.(PHONE).matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.(PHONE);
    if (!mq) return;
    const on = () => setPhone(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return phone;
}

// The app's frame: one bar on every page with the mark, the views the renter chose, Stories, the
// Customize. On a phone the five views are words fixed at the bottom.
// No account, no sign-in: nothing here pretends there is one.
export function AppShell({ section, context, bar, children }: Props) {
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs());
  const [open, setOpen] = useState(false);
  const phone = usePhone();
  const customBtn = useRef<HTMLButtonElement>(null);
  const customPanel = useRef<HTMLElement>(null);
  // Opening moves focus into the panel; Escape closes it and gives focus back to the button.
  useEffect(() => {
    if (open)
      customPanel.current?.querySelector<HTMLElement>("input:not(:disabled), button")?.focus();
  }, [open]);
  const closeCustom = (refocus: boolean) => {
    setOpen(false);
    if (refocus) customBtn.current?.focus();
  };

  const change = (next: Prefs) => {
    setPrefs(next);
    savePrefs(next);
  };
  const shown = TABS.filter((t) => !prefs.hidden.includes(t.id));

  const customizeButton = (
    <button
      ref={customBtn}
      type="button"
      className="app-custom-open"
      aria-expanded={open}
      aria-controls="app-custom"
      onClick={() => setOpen((o) => !o)}
    >
      Customize
    </button>
  );
  const siteLink = SITE_URL ? (
    <a className="app-site" href={SITE_URL}>
      About SNAPBACK
    </a>
  ) : null;

  return (
    <div className="app" data-section={section ?? "none"} data-bar={bar}>
      <header className="app-bar">
        <a className="app-mark" href="/home" aria-label="SNAPBACK home">
          <Lockup />
        </a>
        <nav className="app-tabs" aria-label="Main">
          {shown.map((t) => (
            <a
              key={t.id}
              className="app-tab"
              href={t.href}
              aria-current={section === t.id && !context ? "page" : undefined}
              data-in={section === t.id ? "true" : undefined}
            >
              {t.label}
            </a>
          ))}
          {context && (
            <a className="app-tab app-tab-context" href={context.href} aria-current="page">
              {context.label}
            </a>
          )}
        </nav>
        <div className="app-tools">
          <a className="app-tool app-stories" href="/stories">
            Stories
          </a>
          {!phone && customizeButton}
          {!phone && siteLink}
        </div>
        {open && (
          <section
            id="app-custom"
            className="app-custom"
            aria-label="Customize your space"
            data-testid="customize"
            ref={customPanel}
            onKeyDown={(e) => {
              if (e.key === "Escape") closeCustom(true);
            }}
          >
            <h2 className="app-custom-title">Your space</h2>
            <p className="app-custom-note">
              Pick the views you want in the bar and the one that opens first. Saved in this browser
              only.
            </p>
            <ul className="app-custom-list">
              {TABS.map((t) => {
                const hidden = prefs.hidden.includes(t.id);
                return (
                  <li key={t.id} className="app-custom-row">
                    <label className="app-custom-show">
                      <input
                        type="checkbox"
                        checked={!hidden}
                        disabled={t.id === "home"}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? prefs.hidden.filter((h) => h !== t.id)
                            : [...prefs.hidden, t.id];
                          change({
                            hidden: next,
                            first: next.includes(prefs.first) ? "home" : prefs.first,
                          });
                        }}
                      />
                      {t.label}
                    </label>
                    <label className="app-custom-first">
                      <input
                        type="radio"
                        name="app-first"
                        checked={prefs.first === t.id}
                        disabled={hidden}
                        onChange={() => change({ ...prefs, first: t.id })}
                      />
                      Opens first
                    </label>
                  </li>
                );
              })}
            </ul>
            <button type="button" className="app-custom-done" onClick={() => closeCustom(true)}>
              Done
            </button>
          </section>
        )}
      </header>
      {section !== "home" &&
        (context ? PURPOSE[context.label] : section ? PURPOSE[section] : null) && (
          <p className="app-purpose" data-testid="page-purpose">
            {context ? PURPOSE[context.label] : PURPOSE[section!]}
          </p>
        )}
      {children}
      {phone && section !== "map" && (
        <footer className="app-foot">
          {customizeButton}
          {siteLink}
        </footer>
      )}
    </div>
  );
}

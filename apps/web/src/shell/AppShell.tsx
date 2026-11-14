import { useEffect, useState, type ReactNode } from "react";

import { Wordmark } from "../components/HouseGlyph";
import { loadPrefs, savePrefs, TABS, type Prefs, type Section } from "./prefs";
import { applyTheme, defaultTheme, initialChoice, saveTheme, type ThemeChoice } from "./theme";
import "./shell.css";

export type { Section };

interface Props {
  /** Which main tab the page belongs to. Null: none (a result, a walk). */
  section: Section | null;
  /** A tab for where you are inside a place, shown only while you are there. */
  context?: { label: string; href: string } | null;
  children: ReactNode;
}

// The app's frame: one bar on every page with the mark, the views the renter chose, the light
// or dark switch and Customize. No account, no sign-in: nothing here pretends there is one.
export function AppShell({ section, context, children }: Props) {
  const onMap = section === "map";
  const [picked, setPicked] = useState<ThemeChoice | null>(() =>
    initialChoice(window.location.search),
  );
  const theme: ThemeChoice = picked ?? defaultTheme(onMap);
  useEffect(() => applyTheme(theme), [theme]);
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs());
  const [open, setOpen] = useState(false);

  const pick = (t: ThemeChoice) => {
    setPicked(t);
    saveTheme(t);
  };
  const change = (next: Prefs) => {
    setPrefs(next);
    savePrefs(next);
  };
  const shown = TABS.filter((t) => !prefs.hidden.includes(t.id));

  return (
    <div className="app" data-section={section ?? "none"}>
      <header className="app-bar">
        <a className="app-mark" href="/home" aria-label="SNAPBACK home">
          <Wordmark />
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
          <div className="app-theme" role="group" aria-label="Light, dark or your device's setting">
            {(["light", "dark", "system"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className="app-theme-opt"
                aria-pressed={theme === t}
                onClick={() => pick(t)}
              >
                {t === "light" ? "Light" : t === "dark" ? "Dark" : "Auto"}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="app-custom-open"
            aria-expanded={open}
            aria-controls="app-custom"
            onClick={() => setOpen((o) => !o)}
          >
            Customize
          </button>
        </div>
        {open && (
          <section
            id="app-custom"
            className="app-custom"
            aria-label="Customize your space"
            data-testid="customize"
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
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
            <button type="button" className="app-custom-done" onClick={() => setOpen(false)}>
              Done
            </button>
          </section>
        )}
      </header>
      {children}
    </div>
  );
}

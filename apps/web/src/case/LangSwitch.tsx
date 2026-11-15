// EN | ES on the report. Two buttons, the current one pressed; the page refetches in the
// language chosen. The words on the buttons are the languages' own names, never translated.
import type { Lang } from "../lang";
import "./LangSwitch.css";

const OPTIONS: { lang: Lang; label: string; name: string }[] = [
  { lang: "en", label: "EN", name: "English" },
  { lang: "es", label: "ES", name: "Español" },
];

export function LangSwitch({ lang, onChange }: { lang: Lang; onChange: (lang: Lang) => void }) {
  return (
    <div className="lang-switch" role="group" aria-label="Language" data-testid="lang-switch">
      {OPTIONS.map((o) => (
        <button
          key={o.lang}
          type="button"
          lang={o.lang}
          aria-label={o.name}
          aria-pressed={lang === o.lang}
          onClick={() => onChange(o.lang)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

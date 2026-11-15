// The language of the report: English or Spanish. The API writes the words (?lang=en|es), so
// this only holds the choice. An address with ?lang=es opens in Spanish; otherwise the viewer's
// last choice, remembered in this browser only (storage can be blocked, so every access is
// guarded). The browser's own language is deliberately not read: English is the default.

export type Lang = "en" | "es";

export const LANG_KEY = "snapback.lang";

export const asLang = (value: unknown): Lang | null =>
  value === "es" || value === "en" ? value : null;

export function loadLang(search: string = window.location.search): Lang {
  const asked = asLang(new URLSearchParams(search).get("lang"));
  if (asked) return asked;
  try {
    return asLang(window.localStorage.getItem(LANG_KEY)) ?? "en";
  } catch {
    return "en";
  }
}

export function saveLang(lang: Lang): void {
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    // Blocked storage: the choice holds for this visit only.
  }
}

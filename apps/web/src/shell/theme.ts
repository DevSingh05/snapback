// One theme across the website (outside) and the app (inside), as one attribute on the root
// (`data-theme`), which tokens.css reads. The two themes are Day (the default) and Dusk.
// - The choice lives under one shared key, "snapback-theme". The stored words stay "light" and
//   "dark" (the attribute values the website and tokens.css already read).
// - Migration: an older "system" (follow the device) is dropped, so the page opens in Day; the
//   words "day" and "dusk" are read as light and dark too. There is no OS-follow any more.
// - A link can carry it: `?theme=dusk` (or dark, day, light) applies it and remembers it, so
//   stepping from the website into the app keeps the same look.
// Storage can be blocked, so every access is guarded.

export type Theme = "light" | "dark";
/** Kept as an alias: a choice is always one of the two themes now. */
export type ThemeChoice = Theme;

export const THEME_KEY = "snapback-theme";

/** What the bar calls each theme. */
export const THEME_WORDS: Record<Theme, string> = { light: "Day", dark: "Dusk" };

/** Reads any stored or carried word as a theme: old and new names, never "system". */
export function themeFrom(v: unknown): Theme | null {
  if (v === "light" || v === "day") return "light";
  if (v === "dark" || v === "dusk") return "dark";
  return null;
}

export function savedTheme(): Theme | null {
  try {
    return themeFrom(window.localStorage.getItem(THEME_KEY));
  } catch {
    return null;
  }
}

export function saveTheme(choice: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage is blocked: the choice still holds for this visit.
  }
}

/** A theme carried in the address (`?theme=`), if it names one. */
export function themeFromAddress(search: string): Theme | null {
  return themeFrom(new URLSearchParams(search).get("theme"));
}

/** The choice in force: the address wins and is remembered, else what was saved. */
export function initialChoice(search: string): Theme | null {
  const carried = themeFromAddress(search);
  if (carried) saveTheme(carried);
  return carried ?? savedTheme();
}

/** The theme a page opens in when nothing was chosen: Day, on every page, the map included. */
export const defaultTheme = (): Theme => "light";

export function applyTheme(choice: Theme): void {
  document.documentElement.dataset.theme = choice;
}

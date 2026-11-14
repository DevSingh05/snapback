// One theme across the website (outside) and the app (inside), as one attribute on the root
// (`data-theme`), which tokens.css reads.
// - The choice lives under one shared key, "snapback-theme": "light" | "dark" | "system".
// - A link can carry it: `?theme=dark` (or light, system) applies it and remembers it, so
//   stepping from the website into the app keeps the same look.
// - Until the person has chosen, every page opens in light (Day), the map included.
// - "system" follows the device: the attribute is removed and tokens.css uses the OS setting.
// Storage can be blocked, so every access is guarded.

export type Theme = "light" | "dark";
export type ThemeChoice = Theme | "system";

export const THEME_KEY = "snapback-theme";

const isChoice = (v: unknown): v is ThemeChoice => v === "light" || v === "dark" || v === "system";

export function savedTheme(): ThemeChoice | null {
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return isChoice(v) ? v : null;
  } catch {
    return null;
  }
}

export function saveTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage is blocked: the choice still holds for this visit.
  }
}

/** A theme carried in the address (`?theme=`), if it names one. */
export function themeFromAddress(search: string): ThemeChoice | null {
  const v = new URLSearchParams(search).get("theme");
  return isChoice(v) ? v : null;
}

/** The choice in force: the address wins and is remembered, else what was saved. */
export function initialChoice(search: string): ThemeChoice | null {
  const carried = themeFromAddress(search);
  if (carried) saveTheme(carried);
  return carried ?? savedTheme();
}

/** The theme a page opens in when nothing was chosen. */
export function defaultTheme(onMap?: boolean): Theme {
  void onMap; // Day everywhere, the map included; the argument stays for callers.
  return "light";
}

export function applyTheme(choice: ThemeChoice): void {
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
}

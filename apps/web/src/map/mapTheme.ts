// The city map is the one place with a dark look. Its choice is its own: one attribute on the map
// wrapper (`data-theme` on .city, which tokens.css reads), never on the root, so no other page can
// turn dark. It opens at night (the map reads better dark) and the choice is remembered.
// Storage can be blocked, so every access is guarded.

export type MapTheme = "light" | "dark";

export const MAP_THEME_KEY = "snapback-map-theme";

export function savedMapTheme(): MapTheme {
  try {
    const v = window.localStorage.getItem(MAP_THEME_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    // Storage is blocked: fall through to the default.
  }
  return "dark";
}

export function saveMapTheme(theme: MapTheme): void {
  try {
    window.localStorage.setItem(MAP_THEME_KEY, theme);
  } catch {
    // Storage is blocked: the choice still holds for this visit.
  }
}

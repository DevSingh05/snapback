// What the renter chose for their own space: which tabs show and which opens first.
// Remembered in this browser only; storage can be blocked, so every access is guarded.

export type Section = "home" | "listings" | "map" | "finder" | "replays";

export interface Tab {
  id: Section;
  label: string;
  href: string;
  // False: the page keeps its route but has no place in the top bar (the front cut, focus
  // plan B4). The scam check is the one front door; these are reached from inside a report.
  nav: boolean;
}

export const TABS: Tab[] = [
  { id: "home", label: "Home", href: "/home", nav: true },
  { id: "listings", label: "Listings", href: "/listings", nav: false },
  { id: "map", label: "Map", href: "/map", nav: false },
  { id: "finder", label: "Finder", href: "/finder", nav: false },
  { id: "replays", label: "Replays", href: "/replay", nav: false },
];

/** The tabs the top bar shows. */
export const NAV_TABS: Tab[] = TABS.filter((t) => t.nav);

export interface Prefs {
  hidden: Section[]; // Home can never be hidden
  first: Section; // the tab the site opens on
}

export const DEFAULT_PREFS: Prefs = { hidden: [], first: "home" };
const KEY = "snapback.space";
const IDS = TABS.map((t) => t.id);

export function clean(raw: unknown): Prefs {
  if (typeof raw !== "object" || raw === null) return DEFAULT_PREFS;
  const r = raw as Record<string, unknown>;
  const hidden = Array.isArray(r.hidden)
    ? IDS.filter((id) => id !== "home" && (r.hidden as unknown[]).includes(id))
    : [];
  // Only a tab in the bar can open first, so an old saved "open on Map" lands on Home.
  const first =
    NAV_TABS.map((t) => t.id).find((id) => id === r.first && !hidden.includes(id)) ?? "home";
  return { hidden, first };
}

export function loadPrefs(): Prefs {
  try {
    const text = window.localStorage.getItem(KEY);
    return text ? clean(JSON.parse(text)) : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // Storage is blocked: the choice still holds for this visit.
  }
}

export const tabOf = (id: Section): Tab => TABS.find((t) => t.id === id)!;

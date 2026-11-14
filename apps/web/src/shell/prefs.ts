// What the renter chose for their own space: which tabs show and which opens first.
// Remembered in this browser only; storage can be blocked, so every access is guarded.

export type Section = "home" | "listings" | "map" | "finder" | "replays";

export interface Tab {
  id: Section;
  label: string;
  href: string;
}

export const TABS: Tab[] = [
  { id: "home", label: "Home", href: "/home" },
  { id: "listings", label: "Listings", href: "/listings" },
  { id: "map", label: "Map", href: "/map" },
  { id: "finder", label: "Finder", href: "/finder" },
  { id: "replays", label: "Replays", href: "/replay" },
];

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
  const first = IDS.find((id) => id === r.first && !hidden.includes(id)) ?? "home";
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

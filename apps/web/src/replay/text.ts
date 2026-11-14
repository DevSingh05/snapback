// UI chrome for the replay pages, in English and Spanish. The replay's own text (titles, steps,
// findings) is rendered as the file gives it.

export type Lang = "en" | "es";

export function replayLang(search = window.location.search, nav = navigator.language): Lang {
  const asked = new URLSearchParams(search).get("lang");
  if (asked === "es" || asked === "en") return asked;
  return nav.toLowerCase().startsWith("es") ? "es" : "en";
}

const MONTHS: Record<Lang, string[]> = {
  en: "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" "),
  es: "ene feb mar abr may jun jul ago sep oct nov dic".split(" "),
};

// YYYY-MM-DD in, "Feb 15, 2025" or "15 feb 2025" out. Parsed by hand so the day never shifts.
export function shortDate(iso: string, lang: Lang): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const month = MONTHS[lang][m - 1] ?? "";
  return lang === "es" ? `${d} ${month} ${y}` : `${month} ${d}, ${y}`;
}

const WORDS = {
  en: {
    happened: "What happened",
    withSnapback: "With SNAPBACK",
    navCase: "Real case: Conroe",
    navAll: "All replays",
    indexTitle: "Replays of reported cases",
    indexLead: "Each one follows a case reported in the news, stopped where SNAPBACK would have.",
    source: "Source",
    pattern: { place: "The place", person: "The person", price: "The price" },
    run: "Run this case",
    running: "Starting the case",
    runNeedsApi: "Running a case needs the live API, which is not connected here.",
    runFailed: "Could not start the case. Try again.",
    notSent: "Not sent. Stopped before this.",
    nothingFlagged: "Nothing flagged yet.",
    cantCatch: "What SNAPBACK cannot catch",
    fictional: "Fictional example",
    reportedLabel: "Re-created from a public report",
    footer: (source: string, date: string) =>
      `Replay of a reported case (${source}, ${date}). The listing and house are re-created; no real names.`,
  },
  es: {
    happened: "Lo que pasó",
    withSnapback: "Con SNAPBACK",
    navCase: "Caso real: Conroe",
    navAll: "Todas las repeticiones",
    indexTitle: "Repeticiones de casos denunciados",
    indexLead:
      "Cada una sigue un caso publicado en las noticias, detenido donde SNAPBACK lo habría hecho.",
    source: "Fuente",
    pattern: { place: "El lugar", person: "La persona", price: "El precio" },
    run: "Ejecutar este caso",
    running: "Iniciando el caso",
    runNeedsApi: "Ejecutar un caso necesita la API en vivo, que aquí no está conectada.",
    runFailed: "No se pudo iniciar el caso. Intente de nuevo.",
    notSent: "No se envió. Se detuvo antes de esto.",
    nothingFlagged: "Todavía no hay nada marcado.",
    cantCatch: "Lo que SNAPBACK no puede detectar",
    fictional: "Ejemplo ficticio",
    reportedLabel: "Recreado a partir de un informe público",
    footer: (source: string, date: string) =>
      `Repetición de un caso denunciado (${source}, ${date}). El anuncio y la casa están recreados; no hay nombres reales.`,
  },
};

export function words(lang: Lang) {
  return WORDS[lang];
}

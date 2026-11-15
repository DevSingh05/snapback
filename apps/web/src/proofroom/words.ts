// The Proof Room's own words. Agent names, jobs and tools come from the roster (GET /agents);
// findings and the verdict come from the card. Spanish is kept short on purpose.
import type { DeskState, Lang, Words } from "./model";

export interface RoomWords extends Words {
  room: string;
  replay: string;
  skip: string;
  skipShort: string;
  speed: string;
  held: string;
  state: Record<DeskState, string>;
  waiting: string;
  never: string;
  evidence: string;
  notChecked: string;
  thread: string;
  threadEmpty: string;
  snapback: string;
  deciderRule: string;
  because: string;
  see: string;
  locked: string;
  missing: string;
  fellBack: string;
  liveTab: string;
  meet: string;
  deciderWaits: string;
  notNeeded: string;
  codePlan: string;
  howTab: string;
  traceLede: string;
  traceReplay: string;
  traceRaw: string;
  asked: string;
  said: string;
  planTitle: string;
  sentTo: string;
  noModel: string;
  noModelCalls: string;
  modelCalls: (n: number) => string;
  langsmith: string;
  team: string;
  onIt: string;
  watch: string;
  summary: (checked: number, flags: number) => string;
  how: string;
  seeTeam: string;
  runsOn: string;
  code: string;
  view: string;
  crewView: string;
  diagramView: string;
}

export const WORDS: Record<Lang, RoomWords> = {
  en: {
    room: "PROOF ROOM",
    rest: "Run a check to watch them work",
    checks: (done, total) => `${done} of ${total} checks done`,
    setBy: "code set the result",
    starting: "reading the ad",
    replay: "Replay this run",
    skip: "Skip to the result",
    skipShort: "Skip",
    speed: "Speed",
    held: "A replay holds quick steps for a moment so you can read them. Times shown are the recorded ones.",
    state: {
      idle: "Waiting",
      working: "Working",
      done: "Done",
      skipped: "Not checked",
      unused: "Not used on this case",
    },
    waiting: "Waiting for its turn",
    never: "Never",
    evidence: "Evidence",
    notChecked: "Not checked",
    thread: "What the team is saying",
    threadEmpty: "Nothing yet. The team speaks up as each check starts.",
    snapback: "SNAPBACK",
    deciderRule: "Code sets the verdict. No model can talk a renter into paying.",
    because: "Because",
    see: "See",
    locked:
      "This run opens only in the browser that started the check. Open it from your report there.",
    missing: "We could not find that case.",
    fellBack: "The agent stopped, so code finished the checks.",
    liveTab: "Live",
    meet: "Meet the team",
    deciderWaits: "Waiting for the team's evidence",
    notNeeded: "Not needed for this ad",
    howTab: "See how it worked",
    traceLede:
      "What each member was asked, the tools it used, and what it said back. Code still sets the verdict; this only explains it.",
    traceReplay: "Replay",
    traceRaw: 'Every event is under "Agent trace, raw" at the foot of the page.',
    asked: "Asked",
    said: "Said",
    planTitle: "The plan it wrote",
    sentTo: "Sent work to",
    noModel: "No model ran this step: code checked it.",
    noModelCalls: "no model calls",
    modelCalls: (n) => (n === 1 ? "1 model call" : `${n} model calls`),
    langsmith: "LangSmith",
    codePlan: "Code ran the standard plan and handed out the checks. No model planned this case.",
    team: "Your check team",
    onIt: "Your check team is on it",
    watch: "Watch them work",
    summary: (checked, flags) =>
      `${checked} checked, ${flags === 0 ? "no red flags" : flags === 1 ? "1 found a red flag" : `${flags} found red flags`}`,
    how: "See how they got this",
    seeTeam: "See your check team work",
    runsOn: "Runs on",
    code: "code",
    view: "View",
    crewView: "Crew",
    diagramView: "Diagram",
  },
  es: {
    room: "SALA DE PRUEBAS",
    rest: "Haz una revisión para verlos trabajar",
    checks: (done, total) => `${done} de ${total} comprobaciones hechas`,
    setBy: "el código fijó el resultado",
    starting: "leyendo el anuncio",
    replay: "Repetir esta revisión",
    skip: "Ir al resultado",
    skipShort: "Saltar",
    speed: "Velocidad",
    held: "Los pasos de menos de un segundo se sostienen para poder leerlos. Los tiempos son los grabados.",
    state: {
      idle: "En espera",
      working: "Trabajando",
      done: "Hecho",
      skipped: "No comprobado",
      unused: "No se usó en este caso",
    },
    waiting: "Esperando su turno",
    never: "Nunca",
    evidence: "Pruebas",
    notChecked: "No comprobado",
    thread: "Lo que dice el equipo",
    threadEmpty: "Nada aún. El equipo habla cuando empieza cada comprobación.",
    snapback: "SNAPBACK",
    deciderRule: "El código fija el resultado. Ningún modelo puede convencer a nadie de pagar.",
    because: "Porque",
    see: "Ver",
    locked:
      "Esta revisión solo se abre en el navegador que la empezó. Ábrela desde tu informe allí.",
    missing: "No encontramos ese caso.",
    fellBack: "El agente se detuvo, así que el código terminó las comprobaciones.",
    liveTab: "En vivo",
    meet: "Conoce al equipo",
    deciderWaits: "Esperando las pruebas del equipo",
    notNeeded: "No hizo falta para este anuncio",
    howTab: "Cómo trabajó",
    traceLede:
      "Qué se le pidió a cada miembro, qué herramientas usó y qué respondió. El código fija el resultado; esto solo lo explica.",
    traceReplay: "Repetir",
    traceRaw: 'Cada evento está en "Agent trace, raw" al pie de la página.',
    asked: "Se le pidió",
    said: "Respondió",
    planTitle: "El plan que escribió",
    sentTo: "Envió trabajo a",
    noModel: "Ningún modelo hizo este paso: lo comprobó el código.",
    noModelCalls: "sin llamadas a modelos",
    modelCalls: (n) => (n === 1 ? "1 llamada al modelo" : `${n} llamadas al modelo`),
    langsmith: "LangSmith",
    codePlan:
      "El código siguió el plan estándar y repartió las comprobaciones. Ningún modelo planeó este caso.",
    team: "Tu equipo de revisión",
    onIt: "Tu equipo de revisión está en ello",
    watch: "Verlos trabajar",
    summary: (checked, flags) =>
      `${checked} comprobados, ${flags === 0 ? "sin señales de alerta" : `${flags} con señales de alerta`}`,
    how: "Ver cómo llegaron a esto",
    seeTeam: "Ver a tu equipo de revisión trabajar",
    runsOn: "Funciona con",
    code: "código",
    view: "Vista",
    crewView: "Equipo",
    diagramView: "Diagrama",
  },
};

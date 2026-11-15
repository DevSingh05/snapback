// /under-the-hood: one panel per sponsor track, saying what SNAPBACK uses and where to see it
// working. This file is the whole page's content. The page (HoodPage.tsx) only draws it.
//
// Rules this file keeps (hood.test.tsx pins them):
// - Every number comes from the rubric board's measured "done" items or from an eval result
//   file in this repo, and carries its n and a LIVE / FIXTURE / SYNTHETIC label (hard rules
//   5 and 6). No CoStar record figure (a rent, a phone, a name) ever appears here.
// - Every "Show me" link is a route the router really has.
// - A line that waits on a branch carries `when`, and stays hidden until its switch is on.

/** One switch per piece of work that is not on main yet. When its PR merges, flip its line to
 *  `true`: every panel line, link and number waiting on it appears. Nothing else to edit. The
 *  tests fail if a switch is on while its route or eval file is still missing. */
export const MERGED = {
  /** a/agent-followups: the deep agent picks up to two follow-up checks itself. */
  agentFollowups: false,
  /** f/case-file: the printable case file, at /investigate/case/<group>. */
  caseFile: false,
  /** f/paraphrase-attack: the reworded-ads run, eval/forensics/paraphrase_results.json. */
  paraphraseEval: false,
  /** The real-photo count re-measured on the stricter match bar (#296). Done Nov 15. */
  locateRemeasured: true,
  /** The voice reply timed on a phone, n stated, on the rubric board as a done item. */
  voiceTimed: false,
} as const;

export type Switch = keyof typeof MERGED;
export type Switches = Readonly<Record<Switch, boolean>>;
export type DataLabel = "LIVE" | "FIXTURE" | "SYNTHETIC";

export const LABEL_HINT: Record<DataLabel, string> = {
  LIVE: "Measured on real data in a real run",
  FIXTURE: "Sample data made by the team",
  SYNTHETIC: "Generated data, no real ad or person",
};

interface Gated {
  /** Hidden until this switch is on. Left out: always shown. */
  when?: Switch;
}

export interface Used extends Gated {
  /** The sponsor's technology, or the part of ours, by name. */
  tech: string;
  /** What it does here. */
  text: string;
}

export interface Measured extends Gated {
  /** The figure as shown, e.g. "0 of 48". */
  value: string;
  what: string;
  /** How many it was measured over. Never left out. */
  n: number;
  /** What n counts: "photos", "runs", "rings". */
  unit: string;
  label: DataLabel;
  /** Where the figure comes from: the board item or the eval file's row. Not shown. */
  source: string;
  /** Repo path of the eval file, when the figure comes from one. The test checks it exists. */
  evalFile?: string;
}

export interface ShowLink extends Gated {
  label: string;
  /** A route in App.tsx's matchRoute, with any query that opens the exact state. */
  href: string;
  /** What the screen it opens runs on. */
  data: DataLabel;
}

export interface Panel {
  /** The anchor: /under-the-hood#<id>. */
  id: string;
  sponsor: string;
  track: string;
  /** Two letters for the small mark. Never a logo. */
  mark: string;
  /** One sentence: what it does for the renter or the investigator. */
  does: string;
  used: Used[];
  numbers: Measured[];
  show: ShowLink;
  more: ShowLink[];
  /** A short line under the links, for what cannot be shown in a browser. */
  aside?: string;
  /** The small picture of the Show me screen: a crop of the app's own screen in fixture mode
   *  (assets/hood/show-<id>.webp), or the drawn sample thread. */
  shot: { kind: "screen"; alt: string } | { kind: "thread" };
}

const BOARD = "plan/artifact/board.json";
const LOCATE = "eval/locate_real.csv";
const ADS = "eval/ads_results.csv";
const PARAPHRASE = "eval/forensics/paraphrase_results.json";

export const PANELS: Panel[] = [
  {
    id: "costar",
    shot: {
      kind: "screen",
      alt: "Sample report: the ad's photo beside the same room found in the building's 3D scan",
    },
    sponsor: "CoStar",
    track: "Inside and Out",
    mark: "Co",
    does: "The renter sees the ad's photos placed inside the real building's 3D scan, beside what the record says about that building.",
    used: [
      {
        tech: "CoStar record",
        text: "the building, its manager, website and office phone, checked against the ad. The report hands off to the real listing on Apartments.com.",
      },
      {
        tech: "Matterport scan",
        text: "each ad photo is searched for inside the building's own 3D scan and shown where it lands.",
      },
      {
        tech: "Vexcel aerials",
        text: "the building from above with the photo's true age, on the scan page and the map.",
      },
      {
        tech: "Public records",
        text: "where CoStar has no record: the Texas Comptroller, HUD and Harris County (HCAD), each line under its source.",
      },
    ],
    numbers: [
      {
        // Re-measured on main after #296 raised the strict bar (Nov 15): the same counts.
        when: "locateRemeasured",
        value: "43 of 48",
        what: "real listing photos placed in the right home, 0 in the wrong one",
        n: 48,
        unit: "photos",
        label: "LIVE",
        source: `${LOCATE} locate_real,right_building and locate_real,wrong_building`,
        evalFile: LOCATE,
      },
      {
        value: "0 of 30",
        what: "decoy photos passed off as the claimed building",
        n: 30,
        unit: "decoys",
        label: "LIVE",
        source: `${LOCATE} locate_real,decoy_false_placement`,
        evalFile: LOCATE,
      },
    ],
    show: {
      label: "Show me the photo in the scan",
      href: "/case/sample/twin",
      data: "FIXTURE",
    },
    more: [
      {
        label: "A copied ad: two buildings",
        href: "/case/sample/twin?demo=copied",
        data: "FIXTURE",
      },
      { label: "The city map and aerials", href: "/map", data: "FIXTURE" },
    ],
  },
  {
    id: "langchain",
    shot: {
      kind: "screen",
      alt: "The check team at work round a house: Rules, Record, Phone, Owner and Photo, each with its model",
    },
    sponsor: "LangChain",
    track: "deepagents",
    mark: "Lc",
    does: "The renter watches a planner write a plan for their ad and hand each check to its own sub-agent, then reads who found what.",
    used: [
      {
        tech: "create_deep_agent",
        text: "a planner and one sub-agent per check: record, phone, owner, photos, web.",
      },
      {
        tech: "write_todos and files",
        text: "a plan written per ad; each sub-agent can write only its own note.",
      },
      {
        when: "agentFollowups",
        tech: "Re-planning",
        text: "the agent reads what was not checked and picks up to two follow-up checks, each with its reason.",
      },
      {
        tech: "LangSmith",
        text: "every run is traced, and the trace tab links out to it.",
      },
    ],
    numbers: [
      {
        value: "2.35 s",
        what: "to the agent's first step",
        n: 5,
        unit: "real runs",
        label: "LIVE",
        source: `${BOARD} LangChain: "Background run: first step 2.35 s, done 22.9 s (n=5 real runs, #273)"`,
      },
      {
        value: "22.9 s",
        what: "to the whole team finishing",
        n: 5,
        unit: "real runs",
        label: "LIVE",
        source: `${BOARD} LangChain: "Background run: first step 2.35 s, done 22.9 s (n=5 real runs, #273)"`,
      },
      {
        value: "31 calls",
        what: "to the model in one traced run that ended in Hold",
        n: 1,
        unit: "run",
        label: "LIVE",
        source: `${BOARD} LangChain: "LangSmith trace verified (HOLD in 32 s, 31 model calls, n=1)"`,
      },
    ],
    show: {
      label: "Show me the agent trace",
      href: "/case/deep-sample/twin?team=trace",
      data: "FIXTURE",
    },
    more: [{ label: "Watch the crew work", href: "/case/deep-sample/twin", data: "FIXTURE" }],
  },
  {
    id: "arlequin",
    shot: {
      kind: "screen",
      alt: "The 90-day view on day 45: rings of linked ads, with ring B selected",
    },
    sponsor: "Arlequin",
    track: "AI forensics",
    mark: "Ar",
    does: "The investigator sees which ads belong to one ring, when the ring formed, and the evidence behind every link.",
    used: [
      {
        tech: "Synthetic data only",
        text: "a seeded 90-day stream of ads with rings hidden in it. No real ad, phone or photo.",
      },
      {
        tech: "Link finder",
        text: "shared phones, copied photos and reworded asks tie ads into groups. No model call; the same input gives the same answer.",
      },
      {
        tech: "90-day view",
        text: "drag the day and watch each ring form, with the day it was flagged.",
      },
      {
        when: "caseFile",
        tech: "Case file",
        text: "one ring's ads, links and timeline as a page an investigator can print or export.",
      },
    ],
    numbers: [
      {
        value: "10 of 10",
        what: "rings flagged, in a median of 3 days",
        n: 10,
        unit: "rings",
        label: "SYNTHETIC",
        source: `${BOARD} Arlequin: "90-day view with time to detect: 10/10 rings flagged, median 3 days (synthetic, n=10) (#293)"`,
      },
      {
        value: "0 of 2,684",
        what: "honest ads flagged",
        n: 2684,
        unit: "honest ads",
        label: "SYNTHETIC",
        source: `${BOARD} Arlequin: "0.927 of ring ads caught, 0 of 2,684 honest flagged (SYNTHETIC, n=1 seed, #268)"`,
      },
      {
        // Robustness, with the phone and photo fallback on (the shipped finder once #312
        // merges). Check the figure against the merged file before turning the switch on.
        when: "paraphraseEval",
        value: "9 of 10",
        what: "rings still found after every ring ad is reworded (keyword search: 0 of 10)",
        n: 10,
        unit: "rings",
        label: "SYNTHETIC",
        source: `${PARAPHRASE} variants.paraphrased, finder with the fallback on`,
        evalFile: PARAPHRASE,
      },
    ],
    show: {
      label: "Show me a ring form",
      href: "/investigate?day=45&ring=B",
      data: "SYNTHETIC",
    },
    more: [
      { label: "All 90 days", href: "/investigate", data: "SYNTHETIC" },
      {
        when: "caseFile",
        label: "The case file for group B",
        href: "/investigate/case/B",
        data: "SYNTHETIC",
      },
    ],
  },
  {
    id: "photon",
    shot: { kind: "thread" },
    sponsor: "Photon",
    track: "Messaging agent",
    mark: "Ph",
    does: "The renter forwards the ad in iMessage and gets the verdict, the reason and who to call, in the same thread.",
    used: [
      {
        tech: "Photon Spectrum",
        text: "a Node sidecar on spectrum-ts, live on iMessage. It never texts first.",
      },
      {
        tech: "In",
        text: "the ad as text, screenshots, photos or a voice memo.",
      },
      {
        tech: "Out",
        text: "a checking line, a short report, the card picture and a spoken reply.",
      },
      {
        tech: "Follow-ups",
        text: "why, who do I call and how did you check, answered from the same case. It remembers language, budget and beds.",
      },
    ],
    numbers: [
      {
        // On the board only as an hourly note so far (API reply, n=3), not as a done item.
        when: "voiceTimed",
        value: "0.68 to 0.84 s",
        what: "for the voice API to answer",
        n: 3,
        unit: "calls",
        label: "LIVE",
        source: `${BOARD} team note 23:30-00:30: "Voice API timed (200 in 0.68-0.84 s, n=3)"`,
      },
    ],
    show: {
      label: "Open the link a thread sends",
      href: "/proof-room?case=sample",
      data: "FIXTURE",
    },
    more: [],
    aside: "Live on a phone at our table.",
  },
  {
    id: "amazon",
    shot: {
      kind: "screen",
      alt: "The one box on Home: paste the ad you were sent, then Check it",
    },
    sponsor: "Amazon",
    track: "Best Practical AI",
    mark: "Am",
    does: "The renter pastes any rental ad before paying and gets a plain answer, the reason for it and what to do next.",
    used: [
      {
        tech: "Agents that act",
        text: "a team checks the place, the person and the price. Code sets the verdict; the model only explains it.",
      },
      {
        tech: "It adapts",
        text: "it learns the renter's language, budget and beds, and matches photos even when the ad mirrors them.",
      },
      {
        tech: "Made for one person",
        text: "verdict first, plain words, English and Spanish, by web or by text.",
      },
    ],
    numbers: [
      {
        value: "6 of 6",
        what: "tampered copies of a real listing caught, for each kind of change",
        n: 6,
        unit: "copies per change",
        label: "LIVE",
        source: `${BOARD} Amazon: "Tamper test 6 of 6 per change, LIVE"`,
      },
      {
        value: "117 of 123",
        what: "sample ads and messages given the expected verdict",
        n: 123,
        unit: "ads and messages",
        label: "FIXTURE",
        source: `${BOARD} Amazon: "Batch 117 of 123 (FIXTURE)"; ${ADS}`,
        evalFile: ADS,
      },
      {
        value: "6.8 s",
        what: "from a pasted ad to Hold on the live site",
        n: 1,
        unit: "run",
        label: "LIVE",
        source: `${BOARD} CoStar: "LIVE HOLD in 6.8 s (n=1)"`,
      },
    ],
    show: { label: "Show me a check", href: "/home", data: "LIVE" },
    more: [{ label: "What people who tried it said", href: "/reviews", data: "LIVE" }],
  },
];

const on = (g: Gated, switches: Switches) => g.when === undefined || switches[g.when];

/** A panel with only the lines whose work has merged. */
export function shownPanel(panel: Panel, switches: Switches = MERGED): Panel {
  return {
    ...panel,
    used: panel.used.filter((u) => on(u, switches)),
    numbers: panel.numbers.filter((m) => on(m, switches)),
    more: panel.more.filter((l) => on(l, switches)),
  };
}

export const shownPanels = (switches: Switches = MERGED): Panel[] =>
  PANELS.map((p) => shownPanel(p, switches));

/** The line under a figure: how many, and which kind of data. */
export const nText = (m: Measured): string => `n = ${m.n.toLocaleString("en-US")} ${m.unit}`;

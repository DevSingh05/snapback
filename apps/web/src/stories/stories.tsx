import type { ReactNode } from "react";

import { OfferCard, PicksCard, VerdictView } from "../home/OneBox";
import { PATH_STEPS, type Chapter, type PathStep } from "../ui";
import {
  AD_FILES,
  BROWSE_DRAFT,
  BROWSE_OFFER,
  BROWSE_PICKS,
  BROWSE_WALK,
  BROWSE_WORDS,
  PHOTOS,
  SASCHA_AD,
  SASCHA_CARD,
  SASCHA_CHALLENGE,
  SASCHA_DRAFT,
  SASCHA_PICKS,
  SASCHA_TRACE,
  SASCHA_WALK,
  STUDENT_AD,
  STUDENT_CARD,
  STUDENT_DRAFT,
  STUDENT_PICKS,
  STUDENT_QUESTION,
  STUDENT_WALK,
} from "./data";
import {
  AdScene,
  CheckCard,
  DraftScene,
  ProofScene,
  ThreadScene,
  TypeScene,
  VoiceScene,
  WalkScene,
  type SceneCtx,
} from "./scenes";
import { bot, routed, you } from "./thread";

// Three stories, each a list of beats. A beat is one thing happening in the app: a line of
// narration on the stage, and the app's own screen beside it. People in the stories are
// imagined: Sascha is a judge who gave us the idea, and nothing else about him is stated as fact.

export interface Beat {
  key: string;
  /** A short label for the beat's place on the timeline. */
  label: string;
  /** The narration on the stage, one or two sentences. */
  say: string;
  /** Which of the four path steps this beat belongs to (ui/PathRail). */
  step: PathStep;
  ms: number;
  view: (ctx: SceneCtx) => ReactNode;
}

export interface Story {
  slug: "sascha" | "student" | "browsing";
  /** The story's name on its tab. */
  name: string;
  /** The opening, always framed as imagined. */
  imagine: string;
  /** The story's photograph: its tile, and the ground of its end card. */
  tile: { src: string; alt: string };
  /** What SNAPBACK did that they would otherwise do by hand: the closing line. */
  did: string;
  beats: Beat[];
}

/** The verdict card's three links, as they look, kept on the page so the story keeps playing. */
const VERDICT_ACTS = (
  <>
    <span className="ob-primary">Open the full result</span>
    <span className="ob-secondary st-hot">Walk it first</span>
    <span className="ob-quiet">Get ready to visit</span>
  </>
);

const walkFirst = (p: { has_scan: boolean }) =>
  p.has_scan ? (
    <a className="ob-pick-go st-hot" href="/tour/demo">
      Walk it first
    </a>
  ) : (
    <a className="ob-pick-go" href="/map">
      See on the map
    </a>
  );

const SASCHA_PASTE = SASCHA_AD.body;
/** Once it is in the thread, the pasted ad reads as its first line. */
const SHORT_PASTE = `${SASCHA_AD.body.split(". ")[0]}. …`;

export const STORIES: Story[] = [
  {
    slug: "sascha",
    name: "Sascha moves to Houston",
    imagine:
      "Imagine Sascha is moving to Houston. Sascha is one of our judges, and he gave us this idea.",
    tile: { src: PHOTOS.citySkyline, alt: "Towers on a city skyline" },
    did: "By hand, he'd reverse-search every photo, hunt down the real leasing office, call it in work hours and still face a Zelle deadline. SNAPBACK did it from one paste, and the $600 stayed with him.",
    beats: [
      {
        key: "ad",
        label: "The ad",
        say: "He finds a 1 bed in Midtown on Facebook Marketplace: $1,150. The owner is “working abroad”, so no showings, and wants $600 by Zelle to hold it.",
        step: 1,
        ms: 6000,
        view: () => <AdScene ad={SASCHA_AD} />,
      },
      {
        key: "paste",
        label: "Paste",
        say: "Instead of paying, he pastes the ad and its three photos into one box.",
        step: 1,
        ms: 5000,
        view: (ctx) => <TypeScene words={SASCHA_PASTE} files={AD_FILES} ctx={ctx} />,
      },
      {
        key: "plan",
        label: "The plan",
        say: "The agent reads CoStar's record for the building and works through a plan. The model picks the order; code sets the verdict.",
        step: 1,
        ms: 6500,
        view: (ctx) => (
          <ThreadScene testId="st-plan" entries={[you(SHORT_PASTE, AD_FILES), routed("check")]}>
            <CheckCard events={SASCHA_TRACE} ctx={ctx} />
          </ThreadScene>
        ),
      },
      {
        key: "verdict",
        label: "Verdict",
        say: "Hold off for now. The photos really were taken in this building, but Zelle before a viewing and “no showings” are red flags.",
        step: 1,
        ms: 6500,
        view: () => (
          <ThreadScene testId="st-verdict" entries={[you(SHORT_PASTE, AD_FILES), routed("check")]}>
            <li className="ob-card-row">
              <VerdictView card={SASCHA_CARD} source="fixture" actions={VERDICT_ACTS} />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "proof",
        label: "Proof",
        say: "He sends the poster the drafted photo challenge. Never the money.",
        step: 1,
        ms: 5000,
        view: () => (
          <ProofScene
            text={SASCHA_CHALLENGE}
            you="Sent it myself. Not paying anything until I've seen it."
          />
        ),
      },
      {
        key: "walk",
        label: "Walk it",
        say: "Then he walks the real home. The ad's photo lands in the room it was taken in.",
        step: 2,
        ms: 9000,
        view: (ctx) => <WalkScene set={SASCHA_WALK} ctx={ctx} />,
      },
      {
        key: "places",
        label: "Safer places",
        say: "The Finder shows places like it that have a leasing office on record, and a scan he can walk.",
        step: 3,
        ms: 5000,
        view: () => (
          <ThreadScene
            testId="st-places"
            entries={[
              you("Find me safer places like this."),
              routed("find"),
              bot(
                "Here are 1 beds near Midtown you can walk first. Each has a leasing office on record.",
                "model",
              ),
            ]}
          >
            <li className="ob-card-row">
              <PicksCard picks={SASCHA_PICKS} source="fixture" act={walkFirst} />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "draft",
        label: "Tour request",
        say: "It drafts a tour request to that office. He sends it himself.",
        step: 4,
        ms: 5000,
        view: () => <DraftScene draft={SASCHA_DRAFT} lead="Book me a visit to the first one." />,
      },
      {
        key: "end",
        label: "What it did",
        say: "Sascha keeps his $600.",
        step: 4,
        ms: 6000,
        view: () => null,
      },
    ],
  },
  {
    slug: "student",
    name: "A master's student, from abroad",
    imagine:
      "Imagine a student flying in from abroad for a master's in Houston. She can't see the place before she lands.",
    tile: { src: PHOTOS.airportWindow, alt: "A figure in silhouette at an airport window" },
    did: "By hand, she'd need a friend in Houston to visit, the official office's number, and luck with the wire. SNAPBACK checked the ad and showed her safer places she could walk, from her phone, before any money moved.",
    beats: [
      {
        key: "ad",
        label: "The ad",
        say: "Classes start soon. A studio near campus for $950, the poster is abroad too, and wants an $800 wire to hold it.",
        step: 1,
        ms: 6000,
        view: () => <AdScene ad={STUDENT_AD} />,
      },
      {
        key: "voice",
        label: "Ask",
        say: "She adds the screenshots and just asks out loud.",
        step: 1,
        ms: 5000,
        view: (ctx) => <VoiceScene heard={STUDENT_QUESTION} ctx={ctx} />,
      },
      {
        key: "check",
        label: "The check",
        say: "The box hears a question about an ad, and checks the ad against the record of the real home.",
        step: 1,
        ms: 5500,
        view: (ctx) => (
          <ThreadScene
            testId="st-check"
            entries={[you(STUDENT_QUESTION, AD_FILES), routed("check")]}
          >
            <CheckCard
              events={SASCHA_TRACE.map((e) => ({
                ...e,
                case_id: "ST-STUDENT",
                pick: e.kind === "verdict" ? "dont_pay" : e.pick,
              }))}
              ctx={ctx}
            />
          </ThreadScene>
        ),
      },
      {
        key: "verdict",
        label: "Verdict",
        say: "Don't pay. Two of the photos were taken in a different building, and a wire before a viewing is a red flag.",
        step: 1,
        ms: 6500,
        view: () => (
          <ThreadScene
            testId="st-verdict"
            entries={[you(STUDENT_QUESTION, AD_FILES), routed("check")]}
          >
            <li className="ob-card-row">
              <VerdictView card={STUDENT_CARD} source="fixture" actions={VERDICT_ACTS} />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "places",
        label: "Safer places",
        say: "Then the Finder suggests places near campus with an office on record, and a scan she can walk first.",
        step: 3,
        ms: 6000,
        view: () => (
          <ThreadScene
            testId="st-places"
            entries={[
              you("Find me something safer near campus, under $1,100."),
              routed("find"),
              bot(
                "Here are places near campus you can walk first. Each has a leasing office on record.",
                "model",
              ),
            ]}
          >
            <li className="ob-card-row">
              <PicksCard picks={STUDENT_PICKS} source="fixture" act={walkFirst} />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "walk",
        label: "Walk it",
        say: "She walks the first one, room by room, from the other side of the world.",
        step: 2,
        ms: 8000,
        view: (ctx) => <WalkScene set={STUDENT_WALK} ctx={ctx} />,
      },
      {
        key: "draft",
        label: "Tour request",
        say: "It drafts a tour request to the leasing office on record. She sends it herself.",
        step: 4,
        ms: 5000,
        view: () => <DraftScene draft={STUDENT_DRAFT} lead="Book me a visit to the first one." />,
      },
      {
        key: "end",
        label: "What it did",
        say: "The wire never leaves her account.",
        step: 4,
        ms: 6000,
        view: () => null,
      },
    ],
  },
  {
    slug: "browsing",
    name: "Just looking",
    imagine: "Imagine you're just browsing for a place, with one thing you won't bend on.",
    tile: { src: PHOTOS.citySidewalk, alt: "A city sidewalk between tall buildings" },
    did: "By hand, you'd filter out walk-ups one listing at a time and write to every office. SNAPBACK kept “no walk-ups”, showed you the home room by room and drafted the tour request for you to send.",
    beats: [
      {
        key: "ask",
        label: "Ask",
        say: "You say what you want, in your own words.",
        step: 3,
        ms: 4500,
        view: (ctx) => <TypeScene words={BROWSE_WORDS} ctx={ctx} />,
      },
      {
        key: "keep",
        label: "Keep it",
        say: "The Finder asks before it keeps anything about you.",
        step: 3,
        ms: 5000,
        view: () => (
          <ThreadScene
            testId="st-keep"
            entries={[
              you(BROWSE_WORDS),
              routed("find"),
              bot("Got it: a 1 bed under $1,400 near Montrose.", "policy"),
            ]}
          >
            <li className="ob-card-row">
              <OfferCard
                proposal={BROWSE_OFFER}
                source="fixture"
                onDecided={async () => undefined}
              />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "picks",
        label: "Places",
        say: "You say yes. Every place after this is ranked with it.",
        step: 3,
        ms: 5500,
        view: () => (
          <ThreadScene
            testId="st-picks"
            entries={[
              you(BROWSE_WORDS),
              routed("find"),
              bot("Kept: no walk-ups. Your next places are ranked with it."),
            ]}
          >
            <li className="ob-card-row">
              <PicksCard picks={BROWSE_PICKS} source="fixture" act={walkFirst} />
            </li>
          </ThreadScene>
        ),
      },
      {
        key: "walk",
        label: "Walk it",
        say: "You walk the first one before you go.",
        step: 2,
        ms: 8000,
        view: (ctx) => <WalkScene set={BROWSE_WALK} ctx={ctx} />,
      },
      {
        key: "draft",
        label: "Tour request",
        say: "It drafts a tour request to the leasing office on record. You send it yourself.",
        step: 4,
        ms: 6000,
        view: () => <DraftScene draft={BROWSE_DRAFT} lead="Book me a visit to the first one." />,
      },
      {
        key: "end",
        label: "What it did",
        say: "One visit, booked by you.",
        step: 4,
        ms: 6000,
        view: () => null,
      },
    ],
  },
];

export function storyOf(slug: string | null): Story {
  return STORIES.find((s) => s.slug === slug) ?? STORIES[0]!;
}

export interface StoryChapter extends Chapter {
  /** How long the chapter plays, from its beats. The strip keeps equal segments so every
   *  step's name stays whole. */
  seconds: number;
  /** The first beat of the chapter. */
  first: number;
}

const chapterId = (step: PathStep) => `step-${step}`;

/** The path steps a story passes through, in its own order. */
export function chaptersOf(story: Story): StoryChapter[] {
  const out: StoryChapter[] = [];
  story.beats.slice(0, -1).forEach((b, i) => {
    const last = out[out.length - 1];
    if (last && last.id === chapterId(b.step)) last.seconds += b.ms / 1000;
    else
      out.push({
        id: chapterId(b.step),
        label: PATH_STEPS[b.step - 1]!,
        seconds: b.ms / 1000,
        first: i,
      });
  });
  return out;
}

/** The chapter a beat sits in; none on the end card, where every step is done. */
export function chapterAt(story: Story, index: number): string | null {
  return index >= story.beats.length - 1 ? null : chapterId(story.beats[index]!.step);
}

/** How long a story plays on its own: every beat before the end card. Read from the script. */
export function playsFor(story: Story): number {
  return Math.round(story.beats.slice(0, -1).reduce((t, b) => t + b.ms, 0) / 1000);
}

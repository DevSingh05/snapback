import heroBalconies from "../assets/hero-dusk-balconies.webp";
import sampleBuilding from "../assets/sample-building.webp";
import sampleKitchen from "../assets/sample-kitchen.webp";
import sampleLivingRoom from "../assets/sample-living-room.webp";
import { ChapterStrip, Photo, type Chapter } from "../ui";
import "./landing.css";

// The four-step path on Home: from an ad to a visit you can trust. Each step is a photograph
// and one sentence; the ones the box can run are buttons that run it. "Walk it first" is the
// wide one and carries a small chapter strip, so it reads as a player before it opens. Every
// photo here is licensed stock, stamped as a sample (credits: src/assets/CREDITS.md).

export type StepKey = "check" | "walk" | "find" | "tour";

interface Step {
  key: StepKey;
  note: string;
  title: string;
  text: string;
  src: string;
  alt: string;
}

export const STEPS: readonly Step[] = [
  {
    key: "check",
    note: "Start here",
    title: "Check the ad",
    text: "Its photos, price and payment ask, set against the record of the real home.",
    src: sampleLivingRoom,
    alt: "A living room with a grey sofa and plants",
  },
  {
    key: "walk",
    note: "The real 3D scan",
    title: "Walk it first",
    text: "Move through the real rooms, one by one, before you go or pay. It plays like a video; tap to stop and look around.",
    src: sampleKitchen,
    alt: "A white apartment kitchen with an island and steel appliances",
  },
  {
    key: "find",
    note: "If the check fails",
    title: "Find safer places",
    text: "Leave that ad. Look at verified listings on Apartments.com, or ask for researched homes you can walk first.",
    src: heroBalconies,
    alt: "An apartment building with glass balconies under a pink sky",
  },
  {
    key: "tour",
    note: "You send it, not us",
    title: "Ask for a tour",
    text: "We draft the message and the questions to ask. You read it, then send.",
    src: sampleBuilding,
    alt: "An apartment building seen from below",
  },
];

const ROOMS: Chapter[] = [
  { id: "living", label: "Living room" },
  { id: "kitchen", label: "Kitchen" },
  { id: "bedroom", label: "Bedroom" },
  { id: "bath", label: "Bath" },
];

function StepBody({ step, i, runs }: { step: Step; i: number; runs: boolean }) {
  return (
    <>
      <span className="hiw-meta ui-mono">
        <span>{String(i + 1).padStart(2, "0")}</span>
        <span>{step.note}</span>
      </span>
      <Photo src={step.src} alt={step.alt} stamp="sample" stampAt="top" className="hiw-photo">
        {step.key === "walk" && (
          <ChapterStrip
            chapters={ROOMS}
            current="kitchen"
            onMatte
            label="Rooms in the walk"
            className="hiw-rooms"
          />
        )}
      </Photo>
      <span className="hiw-text">
        <span className="hiw-step-title">
          {step.title}
          {runs && (
            <span className="hiw-arrow" aria-hidden="true">
              {"\u00a0"}→
            </span>
          )}
        </span>
        <span className="hiw-line">{step.text}</span>
      </span>
    </>
  );
}

export function HowItWorks({
  actions = {},
}: {
  // What tapping a step does. A step with no action is shown as text, not as a button.
  actions?: Partial<Record<StepKey, () => void>>;
}) {
  return (
    <section className="hiw" aria-labelledby="hiw-title" data-testid="how-it-works">
      <h2 id="hiw-title" className="hiw-title">
        From an ad to a visit you can trust.
      </h2>
      <p className="hiw-sub">Four steps. Start at any of them; the box above runs them all.</p>
      <ol className="hiw-steps">
        {STEPS.map((step, i) => {
          const run = actions[step.key];
          return (
            <li key={step.key} className="hiw-step" data-step={step.key}>
              {run ? (
                <button type="button" className="hiw-go" onClick={run}>
                  <StepBody step={step} i={i} runs />
                </button>
              ) : (
                <div className="hiw-go">
                  <StepBody step={step} i={i} runs={false} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

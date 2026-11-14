import { Parts } from "../draw/Parts";
import { makeScene, part, type Part } from "../draw/kit";
import { HouseGlyph } from "../components/HouseGlyph";
import { drawRoom } from "../walk/rooms";
import "./landing.css";

// Three real steps, in order, each with a small drawing in the kit's style.

const s = makeScene({ ox: 60, oy: 26 });

// Step 1: the ad as you were sent it: a card with three photos and lines of text.
const AD: Part[] = [
  part("card", [s.contact(0, 0, 70, 96, 8), ...s.box("white", 0, 0, 0, 70, 96, 4)]),
  part("photos", [
    s.onZ("dk-glass", 4.2, 6, 6, 58, 30),
    s.onZ("hiw-thumb", 4.2, 6, 40, 27, 18),
    s.onZ("hiw-thumb", 4.2, 37, 40, 27, 18),
  ]),
  part(
    "text",
    [64, 71, 78].map((y, i) => s.onZ("hiw-text", 4.2, 6, y, i === 2 ? 34 : 58, 3)),
    true,
  ),
  part("price", s.box("teal", 44, 82, 4, 20, 9, 2)),
];

const ROOM = drawRoom("living");

const STEPS = [
  {
    title: "Paste the ad",
    text: "The link, the text or screenshots, just as you were sent it.",
  },
  {
    title: "We check it against the record",
    text: "CoStar's record, the owner and the licence, and the ad's photos placed in the home's 3D scan.",
  },
  {
    title: "Walk it, then contact the office on record",
    text: "See what the ad showed and what it left out, before you pay anything.",
  },
] as const;

export function HowItWorks() {
  return (
    <section className="hiw" aria-label="How it works" data-testid="how-it-works">
      <h2 className="hiw-title">How it works</h2>
      <ol className="hiw-steps">
        {STEPS.map((step, i) => (
          <li key={step.title} className="hiw-step">
            <div className="hiw-art" data-detail="low">
              {i === 0 && (
                <svg viewBox="-36 -8 140 110" aria-hidden="true" focusable="false">
                  <Parts parts={AD} />
                </svg>
              )}
              {i === 1 && (
                <svg viewBox="110 20 580 500" aria-hidden="true" focusable="false">
                  <Parts parts={ROOM.base} />
                  <Parts parts={ROOM.things} />
                </svg>
              )}
              {i === 2 && <HouseGlyph className="hiw-house" detail="low" />}
            </div>
            <p className="hiw-n mono" aria-hidden="true">
              {i + 1}
            </p>
            <h3 className="hiw-step-title">{step.title}</h3>
            <p className="hiw-text">{step.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

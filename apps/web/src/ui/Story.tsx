// Every primitive on one page, for screenshots and for the test that renders them all.
// Opened in dev at /src/ui/story.html (add ?theme=dark for Dusk). Not part of the app build.
import { useState } from "react";

import {
  ChapterStrip,
  EmptyRows,
  Loading,
  Lockup,
  Mark,
  PathRail,
  Photo,
  PhotoPin,
  Problem,
  RecordLine,
  State,
  Tag,
  photoFor,
  type MarkVariant,
  type StateKind,
} from ".";
import "./story.css";

const STATES: StateKind[] = ["ok", "mismatch", "warn", "unconfirmed", "unchecked"];
const MARKS: MarkVariant[] = ["a", "b", "c"];
const ROOMS = [
  { id: "living", label: "Living room", duration: 28 },
  { id: "kitchen", label: "Kitchen", duration: 20 },
  { id: "bed", label: "Bedroom", duration: 20 },
  { id: "bath", label: "Bathroom", duration: 14 },
];
const STEPS = ["Check", "Walk it first", "Safer places", "Tour request"].map((label) => ({
  id: label,
  label,
}));

export function Story() {
  const [room, setRoom] = useState("kitchen");
  const interior = photoFor({ seed: "story-a" });
  const exterior = photoFor({ stock: "exterior", seed: "story-b" });
  const drawn = photoFor({ stock: null }, "the listed home");
  return (
    <main className="st-page">
      <header className="st-head">
        <a href="#top" className="st-lock">
          <Lockup />
        </a>
        <Tag source="fixture" />
      </header>
      <h1>Primitives</h1>

      <section>
        <h2>Mark</h2>
        <div className="st-row">
          {MARKS.map((v) => (
            <a key={v} href="#mark" className="st-marks" data-testid={`mark-${v}`}>
              {[48, 32, 24, 16].map((s) => (
                <Mark key={s} variant={v} size={s} />
              ))}
              <span className="ui-mono">{v === "a" ? "A · default" : v.toUpperCase()}</span>
            </a>
          ))}
          <Mark size={48} lit={false} />
        </div>
        <div className="st-matte ui-on-matte">
          <Lockup onMatte />
          <Tag source="live" />
          <RecordLine source="scan" live />
        </div>
      </section>

      <section>
        <h2>Path rail</h2>
        <PathRail next={2} hrefs={{ 1: "#check", 2: "#walk" }}>
          <span>Case 7Q2M</span>
          <Tag source="fixture" />
        </PathRail>
        <PathRail next={null}>
          <Tag source="live" />
        </PathRail>
      </section>

      <section>
        <h2>State, tag and record line</h2>
        <ul className="st-rows">
          {STATES.map((kind) => (
            <li key={kind}>
              <span>
                A row about the home
                <RecordLine
                  source={kind === "ok" ? "costar" : kind === "mismatch" ? "county" : "license"}
                  date={kind === "ok" ? "Nov 2026" : null}
                  live={kind === "ok"}
                />
              </span>
              <State kind={kind} />
            </li>
          ))}
        </ul>
        <p className="st-tags">
          <Tag source="live" /> <Tag source="fixture" />
        </p>
      </section>

      <section>
        <h2>Photo</h2>
        <div className="st-photos">
          <Photo src={interior.src} alt={interior.alt} stamp={interior.stamp} eager>
            <PhotoPin n={1} x={30} y={40} />
            <PhotoPin n={2} x={62} y={58} />
          </Photo>
          <Photo src={exterior.src} alt={exterior.alt} stamp="ad" eager />
          <Photo src={interior.src} alt={interior.alt} stamp="scan" stampAt="top" eager />
          <Photo src={drawn.src} alt={drawn.alt} stamp={drawn.stamp} />
        </div>
      </section>

      <section>
        <h2>Chapter strip</h2>
        <ChapterStrip chapters={ROOMS} current={room} onSelect={setRoom} label="Rooms" />
        <div className="st-matte">
          <ChapterStrip chapters={ROOMS} current={room} onSelect={setRoom} onMatte label="Rooms" />
        </div>
        <ChapterStrip chapters={STEPS} current="Walk it first" label="Steps" />
      </section>

      <section className="st-three">
        <div>
          <h2>Empty</h2>
          <EmptyRows
            message="Nothing checked yet. Paste an ad above and it will be kept here for 24 hours."
            examples={["2 bed near Rice, $1,400, deposit by Zelle", "Studio in Midtown, no tour"]}
            action={{ label: "Clear filters", onClick: () => undefined }}
          />
        </div>
        <div>
          <h2>Loading</h2>
          <Loading label="Reading the ad" rows={3} />
          <Loading label="Loading the 3D view" shape="photo" />
        </div>
        <div>
          <h2>Problem</h2>
          <Problem
            message="We couldn't read that link. Paste the ad's text or add screenshots instead."
            action={{ label: "Try again", onClick: () => undefined }}
          />
          <label className="st-field">
            A quiet field
            <input type="text" placeholder="Paste an ad" />
          </label>
        </div>
      </section>
    </main>
  );
}

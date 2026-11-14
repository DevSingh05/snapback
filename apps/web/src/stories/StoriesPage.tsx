import { useEffect, useMemo, useRef, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { PHOTOS } from "./data";
import { useStoryPlayer } from "./player";
import { EndScene } from "./scenes";
import { playsFor, STORIES, storyOf, type Story } from "./stories";
import "./stories.css";

// /stories: three renters' stories, each played out on the real app with sample data. Made for
// live demos, the video and the pitch: press play, or step through by hand. A link with
// ?story=<slug> opens on that story with the player in view.

const typing = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  Boolean(el.closest("input, textarea, select, button, a, [role=tab]") || el.isContentEditable);

export function StoriesPage({ reduced: forced }: { reduced?: boolean } = {}) {
  const prefers = usePrefersReducedMotion();
  const reduced = forced ?? prefers;
  const asked = useRef(new URLSearchParams(window.location.search).get("story"));
  const [slug, setSlug] = useState(() => asked.current ?? STORIES[0]!.slug);
  const story = storyOf(slug);
  const stage = useRef<HTMLDivElement>(null);
  const pick = (s: Story, show = false) => {
    setSlug(s.slug);
    const url = new URL(window.location.href);
    url.searchParams.set("story", s.slug);
    window.history.replaceState(null, "", url.pathname + url.search);
    if (show) stage.current?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  };
  // A link to one story lands on its player.
  useEffect(() => {
    if (asked.current) stage.current?.scrollIntoView?.({ block: "start" });
  }, []);
  const at = STORIES.indexOf(story);
  const after = STORIES[at + 1] ?? null;

  return (
    <div className="st" data-testid="stories">
      <section className="st-hero" aria-labelledby="st-title">
        <img
          className="st-hero-img"
          src={PHOTOS.cityStreet}
          alt="A street between tall buildings"
        />
        <span className="st-stamp">Sample photo</span>
        <div className="st-hero-text">
          <h1 id="st-title" className="st-title">
            Three ways this goes.
          </h1>
          <p className="st-lead">
            Watch each one play out on the real app, with sample data. Every person and every number
            in them is “imagine”.
          </p>
          <p className="st-tag">
            <SourceChip source="fixture" />
          </p>
        </div>
      </section>

      <div className="st-picks" role="tablist" aria-label="Stories">
        {STORIES.map((s, i) => (
          <button
            key={s.slug}
            type="button"
            role="tab"
            id={`st-tab-${s.slug}`}
            aria-selected={s.slug === story.slug}
            aria-controls="st-stage"
            className="st-pick"
            onClick={() => pick(s, true)}
          >
            <span className="st-pick-n mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="st-pick-photo">
              <img src={s.backdrop} alt="" />
            </span>
            <span className="st-pick-text">
              <span className="st-pick-name">{s.name}</span>
              <span className="st-pick-line">{s.imagine}</span>
              <span className="st-pick-go">Plays in {playsFor(s)} seconds →</span>
            </span>
          </button>
        ))}
      </div>

      <div ref={stage} className="st-anchor">
        <StoryStage
          key={story.slug}
          story={story}
          reduced={reduced}
          next={after ? { label: after.name, onGo: () => pick(after) } : null}
        />
      </div>

      <p className="st-credit">
        Photos: Unsplash, under the Unsplash License, credited in docs/CREDITS.md. Each one stands
        in for a listing photo or a scan, and says so.
      </p>
    </div>
  );
}

function StoryStage({
  story,
  reduced,
  next,
}: {
  story: Story;
  reduced: boolean;
  next: { label: string; onGo: () => void } | null;
}) {
  const durations = useMemo(() => story.beats.map((b) => b.ms), [story]);
  const player = useStoryPlayer(durations, reduced);
  const beat = story.beats[player.index]!;
  const total = story.beats.length;

  // Space plays and pauses, the arrows step, R restarts. Caught first, so the walk player on a
  // walk beat leaves the keys to the story.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      if (e.key === " " || e.key === "k") player.toggle();
      else if (e.key === "ArrowRight") player.next();
      else if (e.key === "ArrowLeft") player.previous();
      else if (e.key === "r" || e.key === "R") player.restart();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  const ctx = { playing: player.playing, reduced, ms: beat.ms };
  const isEnd = beat.key === "end";
  const playLabel = player.ended ? "Play again" : player.playing ? "Pause" : "Play";

  return (
    <section
      id="st-stage"
      className="st-stage"
      role="tabpanel"
      aria-labelledby={`st-tab-${story.slug}`}
      data-story={story.slug}
      data-beat={beat.key}
      data-playing={player.playing || undefined}
      data-motion={reduced ? "reduced" : "full"}
    >
      <div className="st-frame" data-walk={beat.key === "walk" || undefined}>
        <img className="st-backdrop" src={story.backdrop} alt="" />
        <div className="st-scrim" aria-hidden="true" />
        <span className="st-stamp">Sample photo</span>
        {isEnd ? (
          <EndScene line={story.did} onAgain={player.restart} next={next} />
        ) : (
          <div
            className="st-app"
            key={`${beat.key}-${player.epoch}`}
            data-testid={`st-beat-${beat.key}`}
            data-wide={beat.key === "walk" || undefined}
          >
            {beat.view(ctx)}
          </div>
        )}
      </div>

      <div className="st-caption">
        <p className="st-count mono" aria-hidden="true">
          {String(player.index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")} ·{" "}
          {beat.label}
        </p>
        <div className="st-words">
          <p className="st-imagine">{story.imagine}</p>
          <p
            className="st-line"
            key={`${beat.key}-${player.epoch}`}
            aria-live="polite"
            data-testid="st-line"
          >
            {beat.say}
          </p>
        </div>
      </div>

      <div className="st-bar" role="group" aria-label="Story player">
        <div className="st-ctrls">
          <button
            type="button"
            className="st-ctl st-play"
            onClick={player.toggle}
            aria-label={playLabel}
            data-testid="st-play"
          >
            <Icon name={player.playing ? "pause" : "play"} />
          </button>
          <button
            type="button"
            className="st-ctl"
            onClick={player.previous}
            disabled={player.index === 0}
            aria-label="Back one step"
          >
            <Icon name="back" />
          </button>
          <button
            type="button"
            className="st-ctl"
            onClick={player.next}
            disabled={player.ended}
            aria-label="Forward one step"
          >
            <Icon name="next" />
          </button>
          <button type="button" className="st-ctl" onClick={player.restart} aria-label="Restart">
            <Icon name="restart" />
          </button>
        </div>
        <div className="st-segs">
          {story.beats.map((b, i) => (
            <button
              key={b.key}
              type="button"
              className="st-seg"
              data-state={i < player.index ? "done" : i === player.index ? "now" : "next"}
              aria-current={i === player.index ? "step" : undefined}
              aria-label={`Beat ${i + 1}: ${b.label}`}
              onClick={() => player.go(i)}
            >
              <span className="st-seg-track">
                <span
                  className="st-seg-fill"
                  key={`${i}-${player.index}-${player.epoch}`}
                  style={i === player.index ? { animationDuration: `${b.ms}ms` } : undefined}
                />
              </span>
              <span className="st-seg-name">
                <span className="mono">{String(i + 1).padStart(2, "0")}</span> {b.label}
              </span>
            </button>
          ))}
        </div>
        <p className="st-keys mono">
          {reduced ? "Reduced motion: press play or step. " : ""}Space play or pause · arrows step ·
          R restart
        </p>
      </div>
    </section>
  );
}

function Icon({ name }: { name: "play" | "pause" | "back" | "next" | "restart" }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      {name === "play" ? (
        <path d="M8 5v14l11-7z" fill="currentColor" />
      ) : name === "pause" ? (
        <path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" />
      ) : name === "back" ? (
        <path d="M6 5h2v14H6zM20 5v14L9 12z" fill="currentColor" />
      ) : name === "next" ? (
        <path d="M16 5h2v14h-2zM4 5v14l11-7z" fill="currentColor" />
      ) : (
        <path
          d="M5 12a7 7 0 1 0 2.05-4.95M5 4v4h4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="square"
        />
      )}
    </svg>
  );
}

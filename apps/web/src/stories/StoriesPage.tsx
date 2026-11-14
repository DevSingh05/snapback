import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { SourceChip } from "../components/SourceChip";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { ChapterStrip, Photo } from "../ui";
import { PHOTOS } from "./data";
import { useStoryPlayer } from "./player";
import { EndScene } from "./scenes";
import { chapterAt, chaptersOf, playsFor, STORIES, storyOf, type Story } from "./stories";
import "./stories.css";

// /stories: three renters' stories, each played out on the real app with sample data. Made for
// live demos, the video and the pitch: press play, or step through by hand. A link with
// ?story=<slug> opens on that story with the player in view.

const typing = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  Boolean(el.closest("input, textarea, select, button, a, [role=tab]") || el.isContentEditable);

const two = (n: number) => String(n).padStart(2, "0");

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
      {/* data-bar="photo": the shell lays its bar over this photograph (design ticket 1). */}
      <section className="st-hero" data-bar="photo" aria-labelledby="st-title">
        <Photo
          className="st-hero-photo"
          src={PHOTOS.cityStreet}
          alt="A street between tall buildings"
          stamp="sample"
          hero
          eager
        />
        <div className="st-hero-in ui-on-matte">
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
            <span className="st-pick-n ui-mono">{two(i + 1)}</span>
            <Photo
              className="st-pick-photo"
              src={s.tile.src}
              alt={s.tile.alt}
              stamp="sample"
              eager
            />
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
          number={at + 1}
          reduced={reduced}
          next={after ? { label: after.name, onGo: () => pick(after) } : null}
        />
      </div>

      <p className="st-credit">
        Photos: Unsplash, under the Unsplash License, credited in docs/CREDITS.md. Each one is a
        sample, and says so.
      </p>
    </div>
  );
}

function StoryStage({
  story,
  number,
  reduced,
  next,
}: {
  story: Story;
  number: number;
  reduced: boolean;
  next: { label: string; onGo: () => void } | null;
}) {
  const durations = useMemo(() => story.beats.map((b) => b.ms), [story]);
  const chapters = useMemo(() => chaptersOf(story), [story]);
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
  const isWalk = beat.key === "walk";
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
      <div className="st-stage-in">
        <header className="st-open ui-on-matte">
          <p className="st-open-n ui-mono">Story {two(number)}</p>
          <h2 className="st-imagine">{story.imagine}</h2>
        </header>

        <div className="st-frame" data-testid="st-frame">
          {isEnd ? (
            <EndScene line={story.did} photo={story.tile} onAgain={player.restart} next={next} />
          ) : isWalk ? (
            <div
              className="st-app st-app-wide"
              key={`${beat.key}-${player.epoch}`}
              data-testid={`st-beat-${beat.key}`}
            >
              {beat.view(ctx)}
            </div>
          ) : (
            <Fit key={`${beat.key}-${player.epoch}`} testId={`st-beat-${beat.key}`}>
              {beat.view(ctx)}
            </Fit>
          )}
        </div>

        <div className="st-caption ui-on-matte">
          <p className="st-count ui-mono" aria-hidden="true">
            {two(player.index + 1)} / {two(total)} · {beat.label}
          </p>
          <p
            className="st-line"
            key={`${beat.key}-${player.epoch}`}
            aria-live="polite"
            data-testid="st-line"
          >
            {beat.say}
          </p>
        </div>

        <div className="st-bar ui-on-matte" role="group" aria-label="Story player">
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
          <ChapterStrip
            className="st-chapters"
            chapters={chapters}
            current={chapterAt(story, player.index)}
            onSelect={(id) => player.go(chapters.find((c) => c.id === id)?.first ?? 0)}
            onMatte
            label="The path, step by step"
          />
          <p className="st-keys ui-mono">
            {reduced ? "Reduced motion: press play or step. " : ""}Space play or pause · arrows step
            · R restart
          </p>
        </div>
      </div>
    </section>
  );
}

// The app's own screen, laid out at a width it is at home in and then scaled as a whole until
// all of it sits inside the frame. Nothing is cropped and nothing scrolls. Of the widths tried,
// the one that ends up largest on screen wins, so a long card is laid out wider and a short one
// narrower.
const WIDE = [560, 680, 800, 920, 1040];
const TALL = [340, 380, 430, 480];
const MAX_SCALE = 1.15;

function Fit({ children, testId }: { children: ReactNode; testId: string }) {
  const box = useRef<HTMLDivElement>(null);
  const page = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const b = box.current;
    const el = page.current;
    if (!b || !el) return;
    const fit = () => {
      const w = b.clientWidth;
      const h = b.clientHeight;
      if (!w || !h) return;
      let best = { width: 0, scale: 0 };
      const drafts = el.querySelectorAll("textarea");
      for (const width of w < h ? TALL : WIDE) {
        el.style.width = `${width}px`;
        // A drafted message shows whole, not through a scrolling box.
        for (const t of drafts) {
          t.style.height = "auto";
          if (t.scrollHeight > t.clientHeight) t.style.height = `${t.scrollHeight + 2}px`;
        }
        const scale = Math.min(w / width, h / Math.max(1, el.offsetHeight), MAX_SCALE);
        if (scale > best.scale) best = { width, scale };
      }
      el.style.width = `${best.width}px`;
      for (const t of drafts) {
        t.style.height = "auto";
        if (t.scrollHeight > t.clientHeight) t.style.height = `${t.scrollHeight + 2}px`;
      }
      el.style.transform = `translate(-50%, -50%) scale(${best.scale})`;
    };
    fit();
    if (typeof ResizeObserver !== "function") return;
    // The frame resizes with the window; the screen grows as a beat types or counts up.
    const seen = new ResizeObserver(fit);
    seen.observe(b);
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  return (
    <div ref={box} className="st-fit">
      <div ref={page} className="st-app" data-testid={testId}>
        {children}
      </div>
    </div>
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

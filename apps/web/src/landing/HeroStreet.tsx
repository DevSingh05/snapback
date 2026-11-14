import heroDay from "../assets/hero-day-brick.webp";
import heroDusk from "../assets/hero-dusk-warm.webp";
import "./landing.css";

// Home's hero: a real photograph of an apartment building under the matte scrim. Two files, one
// in daylight and one at dusk, stacked; the theme decides which shows and they crossfade when it
// changes (landing.css). Licensed stock, credited in src/assets/CREDITS.md and stamped as a
// sample: neither is claimed to be a listed home or to be in Houston.

export const HERO_PHOTOS = {
  day: {
    src: heroDay,
    alt: "A brick apartment building with balconies, seen from the street in daylight",
    credit: "Seb Doe",
  },
  dusk: {
    src: heroDusk,
    alt: "An apartment building with balconies, catching the last light at dusk",
    credit: "Duncan Shaffer",
  },
} as const;

export function HeroStreet({ strip = false }: { strip?: boolean }) {
  return (
    <div className={`hs${strip ? " hs-strip" : ""}`} data-testid="hero-street">
      <img
        className="hs-img hs-day"
        src={HERO_PHOTOS.day.src}
        alt={HERO_PHOTOS.day.alt}
        data-testid="hero-photo"
        decoding="async"
      />
      <img
        className="hs-img hs-dusk"
        src={HERO_PHOTOS.dusk.src}
        alt={HERO_PHOTOS.dusk.alt}
        data-testid="hero-photo-dusk"
        decoding="async"
      />
      <span className="hs-scrim" aria-hidden="true" />
      {!strip && <p className="hs-stamp ui-mono">Sample photo · Unsplash</p>}
    </div>
  );
}

// Each member's mark: a flat two-tone glyph on a square plate, in the same language as the
// SNAPBACK house mark (ink shapes, one accent, sharp corners). The frame around the plate is
// the member's state, and always sits beside the state in words. No faces, no photographs.
// Decoration only: aria-hidden, the node's label carries the meaning.
import type { ReactNode } from "react";

const GLYPHS: Record<string, ReactNode> = {
  // a list with one box ticked off: the plan
  planner: (
    <>
      <rect className="g-ink" x="3" y="4" width="18" height="3.4" />
      <rect className="g-ink" x="3" y="10.3" width="18" height="3.4" />
      <rect className="g-ink" x="3" y="16.6" width="10" height="3.4" />
      <rect className="g-act" x="16" y="16.6" width="5" height="3.4" />
    </>
  ),
  // a ruler: the ad measured against the rules
  rules: (
    <>
      <rect className="g-ink" x="2" y="7.5" width="20" height="9" />
      <rect className="g-cut" x="5" y="7.5" width="1.6" height="4.5" />
      <rect className="g-cut" x="9" y="7.5" width="1.6" height="3" />
      <rect className="g-cut" x="13" y="7.5" width="1.6" height="4.5" />
      <rect className="g-cut" x="17" y="7.5" width="1.6" height="3" />
      <rect className="g-act" x="2" y="18" width="9" height="2" />
    </>
  ),
  // the building on the record
  record: (
    <>
      <rect className="g-ink" x="4" y="3" width="10" height="18" />
      <rect className="g-act" x="14" y="10" width="6" height="11" />
      <rect className="g-cut" x="6.2" y="5.5" width="2.2" height="2.2" />
      <rect className="g-cut" x="9.8" y="5.5" width="2.2" height="2.2" />
      <rect className="g-cut" x="6.2" y="9.8" width="2.2" height="2.2" />
      <rect className="g-cut" x="9.8" y="9.8" width="2.2" height="2.2" />
      <rect className="g-cut" x="7.8" y="16" width="2.6" height="5" />
    </>
  ),
  // a phone, its one button in the accent
  phone_office: (
    <>
      <rect className="g-ink" x="7" y="2.5" width="10" height="19" />
      <rect className="g-cut" x="8.8" y="5" width="6.4" height="10.5" />
      <rect className="g-act" x="10.7" y="17.2" width="2.6" height="2.6" />
    </>
  ),
  // a key: who holds the right to rent it
  owner_licence: (
    <>
      <rect className="g-ink" x="2.5" y="7" width="9" height="10" />
      <rect className="g-cut" x="5.2" y="10.2" width="3.6" height="3.6" />
      <rect className="g-ink" x="11.5" y="10.8" width="10" height="2.4" />
      <rect className="g-act" x="16" y="13.2" width="2" height="3.4" />
      <rect className="g-act" x="19.5" y="13.2" width="2" height="2.4" />
    </>
  ),
  // a framed photo
  photo: (
    <>
      <rect className="g-ink" x="2.5" y="4.5" width="19" height="15" />
      <rect className="g-cut" x="4.5" y="6.5" width="15" height="11" />
      <path className="g-ink" d="M4.5 17.5 L9.5 11 L12.6 14.6 L14.6 12.4 L19.5 17.5 Z" />
      <rect className="g-act" x="14.6" y="8" width="2.8" height="2.8" />
    </>
  ),
  // the open web: a grid of pages, one lit
  web: (
    <>
      <rect className="g-ink" x="3" y="3" width="8" height="8" />
      <rect className="g-ink" x="13" y="3" width="8" height="8" />
      <rect className="g-ink" x="3" y="13" width="8" height="8" />
      <rect className="g-act" x="13" y="13" width="8" height="8" />
      <rect className="g-cut" x="5" y="5" width="4" height="1.6" />
      <rect className="g-cut" x="15" y="5" width="4" height="1.6" />
      <rect className="g-cut" x="5" y="15" width="4" height="1.6" />
    </>
  ),
  // a search lens
  finder: (
    <>
      <rect className="g-ink" x="3" y="3" width="13" height="13" />
      <rect className="g-cut" x="5.6" y="5.6" width="7.8" height="7.8" />
      <path className="g-act" d="M14.2 16.2 L16.2 14.2 L21.5 19.5 L19.5 21.5 Z" />
    </>
  ),
  // a route through the home: start, turn, stop
  tour_prep: (
    <>
      <rect className="g-ink" x="3" y="16" width="5" height="5" />
      <rect className="g-ink" x="4.6" y="6.6" width="1.8" height="9.4" />
      <rect className="g-ink" x="4.6" y="4.8" width="11.4" height="1.8" />
      <rect className="g-act" x="16" y="3" width="5" height="5" />
    </>
  ),
  // a stamp
  decider: (
    <>
      <rect className="g-ink" x="8.5" y="2.5" width="7" height="6" />
      <rect className="g-ink" x="10.6" y="8.5" width="2.8" height="4" />
      <rect className="g-ink" x="4" y="12.5" width="16" height="5" />
      <rect className="g-act" x="4" y="19.2" width="16" height="2.3" />
    </>
  ),
};

export const AVATAR = 48;

export function Avatar({ id }: { id: string }) {
  return (
    <svg
      className="pr-avatar"
      width={AVATAR}
      height={AVATAR}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
    >
      <rect className="pr-avatar-pulse" x="1.5" y="1.5" width="45" height="45" />
      <rect className="pr-avatar-plate" x="1.5" y="1.5" width="45" height="45" />
      <g transform="translate(9 9) scale(1.25)">{GLYPHS[id] ?? GLYPHS.planner}</g>
    </svg>
  );
}

export const hasGlyph = (id: string) => id in GLYPHS;

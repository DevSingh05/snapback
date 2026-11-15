// Each member's badge: a round portrait of its character (hat, build and prop) in the member's
// own colour. One family, one light from the left, no faces. It is the member's mark wherever
// it shows: on its name tag in the scene, in its speech bubble, beside its lines in the thread,
// on its card and in the strips. Decoration only: aria-hidden, the name beside it carries the
// meaning.
import type { ReactNode } from "react";

import "./crew.css";
import { personaOf, type Persona } from "./crew";

// What sits on the head, and what is held at the chest.
const PARTS: Record<Persona, { hat: ReactNode; prop?: ReactNode; face?: ReactNode }> = {
  foreman: {
    hat: (
      <>
        <path className="b-own" d="M11.4 16.4 Q11.4 6.2 20 6.2 Q28.6 6.2 28.6 16.4Z" />
        <rect className="b-own" x="8.4" y="15.2" width="23.2" height="2.8" />
        <rect className="b-dark" x="18.7" y="5.2" width="2.6" height="8.6" />
      </>
    ),
    prop: (
      <>
        <rect className="b-wood" x="23.4" y="26.6" width="10.4" height="12.4" />
        <rect className="b-paper" x="24.8" y="28.8" width="7.6" height="10.2" />
        <rect className="b-teal" x="26.6" y="25.6" width="4" height="2.8" />
        <path className="b-line" d="M26.2 32h4.8M26.2 34.6h4.8" />
      </>
    ),
  },
  inspector: {
    hat: (
      <path
        className="b-own"
        d="M11 16.6 Q11.6 8 20 8 Q28 8 28.8 13.6 L33.6 15.4 L33.6 17.2 L11 17.2Z"
      />
    ),
    prop: (
      <>
        <path className="b-handle" d="M32.2 32.8L36.6 37.6" />
        <circle className="b-glass" cx="28.6" cy="28.8" r="5.6" />
        <path className="b-glint" d="M25.6 27.4a3.4 3.4 0 0 1 2.6-2.2" />
      </>
    ),
  },
  photographer: {
    hat: (
      <>
        <path className="b-own" d="M12.2 14.4 Q12.2 6.4 20 6.4 Q27.8 6.4 27.8 14.4Z" />
        <rect className="b-own" x="6.8" y="12.6" width="7" height="2.2" />
      </>
    ),
    face: (
      <>
        <rect className="b-dark" x="10" y="16" width="20" height="11.6" />
        <rect className="b-dark" x="12.6" y="13.6" width="6" height="3" />
        <rect className="b-teal" x="25.2" y="17.6" width="3" height="2" />
        <circle className="b-paper" cx="20" cy="21.8" r="4.9" />
        <circle className="b-glass-flat" cx="20" cy="21.8" r="3.3" />
        <circle className="b-paper" cx="18.8" cy="20.6" r="0.9" />
      </>
    ),
  },
  clerk: {
    hat: (
      <>
        <rect className="b-own" x="12" y="11.4" width="16" height="2.6" />
        <path className="b-visor" d="M10.6 14 L29.4 14 L33.4 18.6 L6.6 18.6Z" />
      </>
    ),
    prop: (
      <>
        <path className="b-paper" d="M21.6 27.4h5l1.4 1.8h6.4v9.8H21.6Z" />
        <rect className="b-teal" x="21.6" y="31.4" width="12.8" height="2" />
      </>
    ),
  },
  operator: {
    hat: (
      <>
        <circle className="b-hair" cx="20" cy="8.4" r="3.8" />
        <path
          className="b-hair"
          d="M12.6 19 Q12.4 10.6 20 10.6 Q27.6 10.6 27.4 19 Q24 14.4 20 14.4 Q16 14.4 12.6 19Z"
        />
        <path className="b-band" d="M11.4 20.6 A8.6 8.6 0 0 1 28.6 20.6" />
        <rect className="b-own" x="8.8" y="17.6" width="4.4" height="7.2" />
        <rect className="b-own" x="26.8" y="17.6" width="4.4" height="7.2" />
        <path className="b-mic" d="M29 24.8 Q28.6 29.2 23.4 29" />
        <circle className="b-teal" cx="22.6" cy="29" r="1.7" />
      </>
    ),
  },
  registrar: {
    hat: (
      <>
        <rect className="b-own" x="13.4" y="5.6" width="13.2" height="7.4" />
        <rect className="b-dark" x="12.4" y="12" width="15.2" height="2" />
      </>
    ),
    prop: (
      <>
        <rect className="b-dark" x="27" y="23.4" width="3.8" height="6.6" />
        <rect className="b-teal" x="24" y="29.8" width="9.8" height="3.8" />
        <rect className="b-paper" x="22.6" y="35" width="12.6" height="5" />
      </>
    ),
  },
  scout: {
    hat: (
      <>
        <circle className="b-paper" cx="20" cy="5.8" r="2.9" />
        <path className="b-own" d="M12 15 Q12 7.6 20 7.6 Q28 7.6 28 15Z" />
        <rect className="b-paper" x="11.2" y="13.6" width="17.6" height="3" />
      </>
    ),
    prop: (
      <>
        <rect className="b-dark" x="9.4" y="28.6" width="21.2" height="10.4" />
        <rect className="b-glass-flat" x="11" y="30.2" width="18" height="8.8" />
        <path className="b-line" d="M13 33h8M13 35.6h11" />
      </>
    ),
  },
  searcher: {
    hat: (
      <>
        <rect className="b-own" x="13.4" y="6.6" width="13.2" height="7" />
        <rect className="b-own" x="6.4" y="13" width="27.2" height="2.6" />
        <rect className="b-dark" x="13.4" y="11.2" width="13.2" height="1.8" />
      </>
    ),
    prop: (
      <>
        <path className="b-paper" d="M8.6 30 L16 28 L24 30 L31.4 28 V38 L24 40 L16 38 L8.6 40Z" />
        <path className="b-line" d="M16 28v10M24 30v10" />
        <path className="b-route" d="M11 36l4-3 5 2.4 4-3.4 5 1.6" />
      </>
    ),
  },
  guide: {
    hat: (
      <>
        <path className="b-own" d="M12.2 15 Q12.2 7.6 20 7.6 Q27.8 7.6 27.8 15Z" />
        <rect className="b-dark" x="12.2" y="14" width="20.4" height="2.2" />
      </>
    ),
    prop: (
      <>
        <path className="b-handle" d="M31.4 9v30" />
        <path className="b-teal" d="M31.4 9.4 L39 13 L31.4 16.6Z" />
      </>
    ),
  },
  judge: {
    hat: (
      <>
        <rect className="b-dark" x="9.4" y="9.6" width="21.2" height="2.6" />
        <rect className="b-dark" x="13.6" y="6.4" width="12.8" height="3.4" />
      </>
    ),
    prop: (
      <>
        <path className="b-paper" d="M15.6 27.4h8.8l-2.4 7.4h-4Z" />
        <rect className="b-dark" x="28.2" y="24.8" width="3.6" height="6" />
        <rect className="b-teal" x="25.2" y="30.6" width="9.6" height="3.8" />
      </>
    ),
  },
  helper: {
    hat: <path className="b-own" d="M12.2 15 Q12.2 7.6 20 7.6 Q27.8 7.6 27.8 15Z" />,
  },
};

export function Badge({ id, size = 28 }: { id: string; size?: number }) {
  const persona = personaOf(id);
  const part = PARTS[persona];
  const clip = `crew-badge-${id}`;
  return (
    <svg
      className="crew-badge"
      data-who={id}
      data-persona={persona}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      aria-hidden="true"
      focusable="false"
    >
      <clipPath id={clip}>
        <circle cx="20" cy="20" r="18.4" />
      </clipPath>
      <circle className="b-disc" cx="20" cy="20" r="18.4" />
      <g clipPath={`url(#${clip})`}>
        {/* One light from the left: the right of the disc sits a step darker. */}
        <path className="b-disc-shade" d="M20 0h20v40H20Z" />
        <path className="b-coat" d="M4.6 40 Q4.6 27.4 20 27.4 Q35.4 27.4 35.4 40Z" />
        <path className="b-coat-shade" d="M20 27.4 Q35.4 27.4 35.4 40H20Z" />
        <circle className="b-head" cx="20" cy="19.4" r="7.6" />
        <path className="b-head-shade" d="M20 11.8a7.6 7.6 0 0 1 0 15.2Z" />
        {part.face}
        {part.hat}
        {part.prop}
      </g>
      <circle className="b-ring" cx="20" cy="20" r="18.4" />
    </svg>
  );
}

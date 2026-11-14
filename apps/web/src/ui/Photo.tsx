// A photograph, the way every screen shows one: sharp corners, the matte finish from tokens
// (--photo-filter, or --hero-filter for a hero), paper grain over it, and a mono stamp that says
// where it came from. With no src the drawn stand-in ground shows and the stamp says so.
// Children sit over the photo (numbered pins, a chapter strip).
import type { ReactNode } from "react";

import "./ui.css";

export type StampKind = "ad" | "scan" | "record" | "aerial" | "sample" | "drawn";

// The stamp words, the only ones a photo may carry. "scan", "record" and "aerial" are real
// sponsor imagery served at runtime, so they always read LIVE.
export const STAMP_TEXT: Record<StampKind, string> = {
  ad: "FROM THE AD",
  scan: "FROM THE 3D SCAN · LIVE",
  record: "FROM THE RECORD · LIVE",
  aerial: "AERIAL · VEXCEL · LIVE",
  sample: "SAMPLE PHOTO",
  drawn: "DRAWN STAND-IN",
};

const LIVE_STAMPS: ReadonlySet<StampKind> = new Set(["scan", "record", "aerial"]);

interface PhotoProps {
  src: string | null;
  // Describes what is in the frame. Never claims a stock photo is the listed home.
  alt: string;
  // Which stamp to print; null prints none (only for a photo whose caption already says it).
  stamp: StampKind | null;
  // Extra words after the stamp, such as a capture date the API returned.
  stampNote?: string;
  stampAt?: "bottom" | "top";
  // The hero finish (stronger matte, heavier grain).
  hero?: boolean;
  // Above the fold: load at once. Everything else loads lazily.
  eager?: boolean;
  className?: string;
  children?: ReactNode;
}

export function Photo({
  src,
  alt,
  stamp,
  stampNote,
  stampAt = "bottom",
  hero = false,
  eager = false,
  className,
  children,
}: PhotoProps) {
  const kind = stamp === null ? null : src ? stamp : "drawn";
  return (
    <span
      className={`ui-photo${hero ? " ui-photo-hero" : ""}${className ? ` ${className}` : ""}`}
      data-stamp={kind ?? undefined}
    >
      {src ? (
        <img src={src} alt={alt} loading={eager ? "eager" : "lazy"} decoding="async" />
      ) : (
        <span className="ui-photo-none" role="img" aria-label={alt} />
      )}
      {kind && (
        <span
          className={`ui-stamp${stampAt === "top" ? " ui-stamp-top" : ""}${LIVE_STAMPS.has(kind) ? " ui-stamp-live" : ""}`}
        >
          {LIVE_STAMPS.has(kind) && <i aria-hidden="true" />}
          {stampNote ? `${STAMP_TEXT[kind]} · ${stampNote}` : STAMP_TEXT[kind]}
        </span>
      )}
      {children}
    </span>
  );
}

// A numbered pin over a photo: a bone square with an ink number, placed by percent.
export function PhotoPin({ n, x, y }: { n: number; x: number; y: number }) {
  return (
    <span className="ui-pin" style={{ left: `${x}%`, top: `${y}%` }} aria-hidden="true">
      {n}
    </span>
  );
}

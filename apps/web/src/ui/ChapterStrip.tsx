// The chapter strip: one segment per chapter (a room in the Walk, a step in a replay, a path
// step in a story), the current one marked in the accent. Segments are sized by duration only
// when every chapter carries one; otherwise they are equal. With onSelect each segment is a
// button; without it the strip is a read-only list.
import type { CSSProperties } from "react";

import "./ui.css";

export interface Chapter {
  id: string;
  label: string;
  // Seconds, or any one unit, from the timeline in view. Never a guessed number.
  duration?: number;
}

interface ChapterStripProps {
  chapters: Chapter[];
  current?: string | null;
  onSelect?: (id: string) => void;
  // On a matte band or a photograph (the Walk transport); default is plaster.
  onMatte?: boolean;
  label?: string;
  className?: string;
}

export function chapterColumns(chapters: Chapter[]): string {
  const timed = chapters.length > 0 && chapters.every((c) => (c.duration ?? 0) > 0);
  return chapters.map((c) => `minmax(0, ${timed ? c.duration : 1}fr)`).join(" ");
}

export function ChapterStrip({
  chapters,
  current,
  onSelect,
  onMatte = false,
  label = "Chapters",
  className,
}: ChapterStripProps) {
  const style = { "--ui-chapters": chapterColumns(chapters) } as CSSProperties;
  return (
    <ol
      className={`ui-chapters${onMatte ? " ui-on-matte" : ""}${className ? ` ${className}` : ""}`}
      style={style}
      aria-label={label}
    >
      {chapters.map((c) => {
        const on = c.id === current;
        return (
          <li key={c.id} className={on ? "ui-chapter-on" : undefined}>
            {onSelect ? (
              <button
                type="button"
                aria-current={on ? "step" : undefined}
                onClick={() => onSelect(c.id)}
              >
                {c.label}
              </button>
            ) : (
              <span aria-current={on ? "step" : undefined}>{c.label}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

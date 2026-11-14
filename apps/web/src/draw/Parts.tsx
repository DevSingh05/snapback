import type { Part } from "./kit";
import "./draw.css";

/** Draws kit parts in order. Each part is a group named by `data-part`; fine detail carries
 *  the `dk-fine` class so it can be dropped at small sizes (see draw.css). */
export function Parts({ parts }: { parts: Part[] }) {
  return (
    <>
      {parts.map((p, i) => (
        <g key={`${p.name}-${i}`} data-part={p.name} className={p.fine ? "dk-fine" : undefined}>
          {p.prims.map((s, j) =>
            s.k === "poly" ? (
              <polygon key={j} className={s.c} points={s.pts} />
            ) : (
              <line key={j} className={s.c} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
            ),
          )}
        </g>
      ))}
    </>
  );
}

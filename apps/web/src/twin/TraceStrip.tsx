import { useState, type ReactNode } from "react";

// The agent trace, folded into a strip under the twin. Collapsed until the viewer opens it.
export function TraceStrip({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="trace-strip" aria-label="Agent trace strip">
      <button
        type="button"
        className="trace-strip-toggle"
        aria-expanded={open}
        aria-controls="trace-strip-body"
        onClick={() => setOpen((o) => !o)}
      >
        Agent trace
        <span className="mono" aria-hidden="true">
          {open ? "Hide" : "Show"}
        </span>
      </button>
      <div id="trace-strip-body" data-testid="trace-slot" className="twin-trace" hidden={!open}>
        {open ? children : null}
      </div>
    </section>
  );
}

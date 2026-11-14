import { useState } from "react";

import type { DataSource } from "../contracts";
import { embedUrl } from "../twin/showcase";

// When the loaded 3D scan is not the home this walk draws (the sample walk, or a scan that does
// not hold the plan's rooms), the walk stays on the drawing and the scan is offered here, whole
// and honestly named. It is never walked by the player and never passed off as this home's rooms.
export function ScanOffer({
  modelId,
  sdkKey,
  source,
}: {
  modelId: string;
  sdkKey: string;
  source: DataSource;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="scan-offer" data-testid="scan-offer" aria-label="A real 3D scan">
      <div className="scan-offer-head">
        <div>
          <h2 className="scan-offer-title">See a real 3D scan of this building</h2>
          <p className="scan-offer-note" data-testid="scan-offer-note">
            {source === "fixture"
              ? "A real scan from the CoStar kit. The rooms above are a drawn sample, so they will not match it."
              : "A real scan from the CoStar kit. It does not hold the rooms in this walk, so the walk stays on the drawing."}
          </p>
        </div>
        <button
          type="button"
          className="scan-offer-btn"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Close the scan" : "Open the scan"}
        </button>
      </div>
      {open && (
        <div className="scan-offer-frame">
          <iframe
            title="A real 3D scan"
            src={embedUrl(modelId, sdkKey)}
            allow="fullscreen; xr-spatial-tracking"
          />
        </div>
      )}
    </section>
  );
}

// Loading (design v4 section 4): the page's own shape in sharp tone blocks plus one plain line
// that says what is happening. No spinner, no percent, no time estimate, no shimmer loop.
import "./ui.css";

interface LoadingProps {
  // What is happening, in plain words: "Reading the ad", "Loading the 3D view".
  label: string;
  // The shape of what will land: rows (a list), photo (one picture), band (the verdict band).
  shape?: "rows" | "photo" | "band";
  rows?: number;
  className?: string;
}

export function Loading({ label, shape = "rows", rows = 3, className }: LoadingProps) {
  return (
    <div
      className={`ui-loading ui-loading-${shape}${className ? ` ${className}` : ""}`}
      role="status"
      data-testid="loading"
    >
      <p className="ui-loading-label">{label}</p>
      <div className="ui-loading-shape" aria-hidden="true">
        {shape === "rows" ? (
          Array.from({ length: rows }, (_, i) => <span key={i} className="ui-loading-row" />)
        ) : (
          <span className="ui-loading-block" />
        )}
      </div>
    </div>
  );
}

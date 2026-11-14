// A drawn stand-in for an ad photo, used when the real image cannot be shown (the sample walk,
// or a case whose photo did not load). Team-made: a plain one-point view into a room, in the
// app's tokens, and always labelled "stand-in" where it is shown. Never sponsor imagery.
export function StandInPhoto({
  label,
  className,
  small = false,
}: {
  label: string;
  className?: string;
  small?: boolean;
}) {
  return (
    <svg
      className={`sp ${className ?? ""}`.trim()}
      viewBox="0 0 640 400"
      preserveAspectRatio="xMidYMid slice"
      role={label ? "img" : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : true}
      data-testid="stand-in-photo"
    >
      {/* the room: ceiling, side walls, floor, back wall */}
      <polygon className="sp-ceil" points="0,0 640,0 470,92 170,92" />
      <polygon className="sp-wall-l" points="0,0 170,92 170,272 0,400" />
      <polygon className="sp-wall-r" points="640,0 640,400 470,272 470,92" />
      <polygon className="sp-floor" points="0,400 170,272 470,272 640,400" />
      <rect className="sp-back" x="170" y="92" width="300" height="180" />
      {/* floor boards running away from the camera, toward the vanishing point */}
      {!small &&
        [200, 260, 320, 380, 440].map((x) => (
          <line key={x} className="sp-seam" x1={x} y1={272} x2={320 + (x - 320) * 3} y2={452} />
        ))}
      {/* a window in the back wall, with its light falling on the floor */}
      <rect className="sp-window" x="208" y="118" width="112" height="86" />
      {!small && <line className="sp-mullion" x1="264" y1="118" x2="264" y2="204" />}
      <polygon className="sp-light" points="214,272 316,272 314,317 161,317" />
      {/* a counter run along the right wall: its top, the face toward the room, its end */}
      <polygon className="sp-counter-top" points="470,207 395,207 440,222 560,222" />
      <polygon className="sp-counter" points="395,207 440,222 440,326 395,272" />
      <polygon className="sp-counter-end" points="440,222 560,222 560,326 440,326" />
      {!small && (
        <>
          <line className="sp-seam" x1="500" y1="236" x2="500" y2="326" />
          <polygon className="sp-pendant" points="300,130 340,130 348,146 292,146" />
          <line className="sp-cord" x1="320" y1="92" x2="320" y2="130" />
        </>
      )}
      {/* a doorway in the left wall */}
      <polygon className="sp-door" points="132,126 80,110 80,326 132,294" />
    </svg>
  );
}

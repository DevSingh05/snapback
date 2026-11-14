interface Props {
  src: string | null;
  opacity: number; // 0 to 1
  label: string;
}

// A listing photo laid over the 3D view. Opacity is driven by the page so it can crossfade.
export function PhotoOverlay({ src, opacity, label }: Props) {
  if (!src) return null;
  return (
    <img
      className="twin-overlay"
      data-testid="photo-overlay"
      src={src}
      alt={label}
      style={{ opacity }}
    />
  );
}

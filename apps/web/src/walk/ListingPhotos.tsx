import "./walk.css";

export interface ListingPhoto {
  src: string;
  alt: string;
}

interface Props {
  photos: ListingPhoto[];
  /** Where CoStar's record got them, e.g. "Homes.com" or "Apartments.com". */
  site: string;
  /** The record's own as-of line, e.g. "as of CoStar's last research". */
  asOf: string;
}

// The real listing photos on CoStar's record for this home, with their source and date line.
// Nothing is drawn when the record gives none.
export function ListingPhotos({ photos, site, asOf }: Props) {
  if (photos.length === 0) return null;
  return (
    <section className="lp" data-testid="listing-photos" aria-label="Listing photos">
      <header className="lp-head">
        <h2 className="lp-title">Listing photos</h2>
        <p className="lp-source mono" data-testid="listing-source">
          {site}, on CoStar's record · {asOf}
        </p>
      </header>
      <ul className="lp-strip">
        {photos.map((p, i) => (
          <li key={`${i}-${p.src}`} className="lp-item">
            <img className="lp-img" src={p.src} alt={p.alt} loading="lazy" />
          </li>
        ))}
      </ul>
    </section>
  );
}

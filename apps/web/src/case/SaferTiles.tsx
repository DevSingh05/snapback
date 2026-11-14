// The next step after a result that did not pass: at most three researched places that carry a
// way out to their own listing. Each tile is one tap target and opens that listing in a new
// tab. The words on a tile are the API's; the link is used only when it is a plain https one.
import "../ui/ui.css";
import "./case.css";
import { RecordLine } from "../ui";
import { outLink, type SaferPlace } from "./model";

const MAX_TILES = 3;

/** The places that can be handed off, at most three, each with its checked link. */
export function saferTiles(places: SaferPlace[]): { place: SaferPlace; href: string }[] {
  return places
    .flatMap((place) => {
      const href = outLink(place.handoff_url);
      return href ? [{ place, href }] : [];
    })
    .slice(0, MAX_TILES);
}

const onApartments = (href: string) => /(^|\.)apartments\.com$/i.test(new URL(href).hostname);

export function SaferTiles({
  places,
  titleId = "case-safer-title",
}: {
  places: SaferPlace[];
  titleId?: string;
}) {
  const tiles = saferTiles(places);
  if (tiles.length === 0) return null;
  return (
    <section className="case-tiles" aria-labelledby={titleId} data-testid="case-tiles">
      <h2 id={titleId}>A safer next step</h2>
      <p className="case-tiles-lead">
        Researched places like this one. Each opens its own listing, where you can ask for a
        viewing.
      </p>
      <ul>
        {tiles.map(({ place, href }) => (
          <li key={place.property_id}>
            <a href={href} target="_blank" rel="noopener noreferrer" data-testid="case-tile">
              <span className="ui-mono case-tile-kicker">
                {onApartments(href)
                  ? "SAFER: LISTED ON APARTMENTS.COM"
                  : "SAFER: ON COSTAR'S RECORD"}
              </span>
              {place.floor_plan ? <b>{place.floor_plan}</b> : null}
              {place.price_text ? <span>{place.price_text}</span> : null}
              {place.availability_text ? <span>{place.availability_text}</span> : null}
              {place.scan_text ? <span>{place.scan_text}</span> : null}
              {place.office_on_record ? (
                <span>Leasing office on record: {place.office_on_record}</span>
              ) : null}
              <RecordLine source="costar" live={place.source} />
              <span className="case-tile-out">
                {place.handoff_label ?? "Open the listing"} <span aria-hidden="true">↗</span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

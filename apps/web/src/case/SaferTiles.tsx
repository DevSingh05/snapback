// The next step after a result that did not pass: at most three researched places, each led by
// a photo and each one tap target with one way out. A place that carries a hand-off link opens
// its own listing in a new tab; a place without one opens its walk (when a 3D scan is on record)
// or its tour prep here. The words on a tile are the API's; a hand-off link is used only when
// it is a plain https one.
import "../ui/ui.css";
import "./case.css";
import { Photo, RecordLine, photoFor } from "../ui";
import { outLink, type SaferPlace } from "./model";

const MAX_TILES = 3;

export interface SaferTile {
  place: SaferPlace;
  href: string;
  // The words on the tile's one action.
  label: string;
  // True when the link leaves the app (the listing itself).
  out: boolean;
}

const planQuery = (place: SaferPlace) =>
  place.plan_key ? `?plan_key=${encodeURIComponent(place.plan_key)}` : "";

/** At most three tiles, in the API's order, each with its one link. */
export function saferTiles(places: SaferPlace[]): SaferTile[] {
  return places.slice(0, MAX_TILES).map((place) => {
    const out = outLink(place.handoff_url);
    if (out)
      return { place, href: out, label: place.handoff_label ?? "Open the listing", out: true };
    const id = encodeURIComponent(place.property_id);
    return place.has_3d_scan
      ? { place, href: `/tour/${id}${planQuery(place)}`, label: "Walk it first", out: false }
      : { place, href: `/prep/place/${id}${planQuery(place)}`, label: "Tour prep", out: false };
  });
}

const onApartments = (href: string) => /(^|\.)apartments\.com$/i.test(new URL(href).hostname);

function kicker(tile: SaferTile): string {
  if (!tile.out) return "RESEARCHED PLACE";
  return onApartments(tile.href) ? "SAFER: LISTED ON APARTMENTS.COM" : "SAFER: ON COSTAR'S RECORD";
}

export function SaferTiles({
  places,
  id,
  titleId = "case-safer-title",
}: {
  places: SaferPlace[];
  id?: string;
  titleId?: string;
}) {
  const tiles = saferTiles(places);
  if (tiles.length === 0) return null;
  return (
    <section className="case-tiles" id={id} aria-labelledby={titleId} data-testid="case-tiles">
      <h2 id={titleId}>A safer next step</h2>
      <p className="case-tiles-lead">
        Researched places like this one. See the rooms or the listing before you contact anyone.
      </p>
      <ul>
        {tiles.map((tile) => {
          const { place } = tile;
          const photo = photoFor(
            { source: place.source, stock: "exterior", seed: place.property_id },
            "this place",
          );
          return (
            <li key={place.property_id}>
              <a
                href={tile.href}
                data-testid="case-tile"
                {...(tile.out ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              >
                <Photo
                  src={photo.src}
                  alt={photo.alt}
                  stamp={photo.stamp}
                  className="case-tile-photo"
                />
                <span className="case-tile-body">
                  <span className="ui-mono case-tile-kicker">{kicker(tile)}</span>
                  {place.floor_plan ? <b>{place.floor_plan}</b> : null}
                  {place.price_text ? <span>{place.price_text}</span> : null}
                  {place.availability_text ? <span>{place.availability_text}</span> : null}
                  {place.scan_text ? <span>{place.scan_text}</span> : null}
                  {place.office_on_record ? (
                    <span>Leasing office on record: {place.office_on_record}</span>
                  ) : null}
                  <RecordLine source="costar" live={place.source} />
                  <span className="case-tile-out">
                    {tile.label} <span aria-hidden="true">{tile.out ? "↗" : "→"}</span>
                  </span>
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

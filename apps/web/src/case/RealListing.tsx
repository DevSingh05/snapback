// The real listing: the ad on the left, and on the right what CoStar's record holds for the
// building, side by side so a renter can see the gap. Every value and every sentence is a field
// of GET /cases/{id}/real-listing (contracts.ts RealListing): the lead paragraph, the photo
// line and the phone line are written by the API's code, never here. A field the API left out
// is a row left out. Rents show only when the API says figures may be shown. No phone digits
// and no street address ever appear.
import "../ui/ui.css";
import "./case.css";
import { Tag } from "../ui";
import { dollars, outLink, type RealListing as Listing, type RealListingPlan } from "./model";

function rentOf(plan: RealListingPlan): string | null {
  const { rent_min: lo, rent_max: hi } = plan;
  if (lo == null && hi == null) return null;
  if (lo != null && hi != null && lo !== hi) return `${dollars(lo)} to ${dollars(hi)} a month`;
  return `${dollars((lo ?? hi)!)} a month`;
}

/** Where "See the real listing" goes: the API's own link and nothing else. The page never
 *  builds an address from a host name; with no link from the API there is no button. */
export function realListingLink(listing: Listing): string | null {
  return outLink(listing.cta_url);
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="case-real-row">
      <dt className="ui-mono">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function RealListing({
  listing,
  titleId = "case-real-title",
}: {
  listing: Listing;
  titleId?: string;
}) {
  const figures = listing.figures_shown === true;
  const plans = listing.plans ?? [];
  const link = realListingLink(listing);
  const matched = listing.which === "matched";
  return (
    <section className="case-real" aria-labelledby={titleId} data-testid="case-real">
      <header className="case-sheet-head">
        <h2 id={titleId}>The ad, next to the real listing</h2>
        <Tag source={listing.source} testId="real-source" />
      </header>
      {listing.headline ? (
        <p className="case-real-lead" data-testid="real-headline">
          {listing.headline}
        </p>
      ) : null}
      {listing.provenance ? (
        <p className="case-real-prov" data-testid="real-provenance">
          {listing.provenance}
        </p>
      ) : null}
      <div className="case-real-cols">
        <div className="case-real-col" data-side="ad">
          <h3>The ad</h3>
          <dl>
            <Row
              label="Rent"
              value={listing.ad_rent != null ? `${dollars(listing.ad_rent)} a month` : null}
            />
            <Row
              label="Payment"
              value={
                listing.ad_asks_irreversible
                  ? "Asks for money in a way that can't be taken back"
                  : null
              }
            />
            <Row label="Phone" value={listing.phone_line} />
          </dl>
        </div>
        <div className="case-real-col" data-side="record">
          <h3>Its Apartments.com listing on CoStar's record</h3>
          <p className="case-real-which ui-mono">
            {matched ? "THE BUILDING THE PHOTOS MATCH" : "THE BUILDING THE AD NAMES"}
          </p>
          <dl>
            <Row label="Building" value={listing.building_name} />
            <Row label="Managed by" value={listing.manager_company} />
            <Row label="Website" value={listing.website_host} />
            {plans.map((plan, i) => {
              const units =
                plan.units_available != null
                  ? `${plan.units_available} ${plan.units_available === 1 ? "unit" : "units"} reported available`
                  : null;
              const value = [figures ? rentOf(plan) : null, units].filter(Boolean).join(" · ");
              return <Row key={i} label={plan.name ?? "Floor plan"} value={value || null} />;
            })}
          </dl>
          {!figures && plans.length > 0 ? (
            <p className="case-real-note">Rents are not shown on this run.</p>
          ) : null}
          <span className="ui-record" data-testid="real-record">
            COSTAR RECORD · {listing.as_of} · {listing.source === "live" ? "LIVE" : "FIXTURE"}
          </span>
          {link ? (
            <a
              className="ui-btn-quiet case-real-link"
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="real-link"
            >
              {listing.cta_label ?? "See the real listing"} <span aria-hidden="true">↗</span>
            </a>
          ) : null}
        </div>
      </div>
    </section>
  );
}

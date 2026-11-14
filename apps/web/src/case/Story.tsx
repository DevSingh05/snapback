// The case pieces on one page, for screenshots and layout checks. Opened in dev at
// /src/case/story.html. Not part of the app build.
// Everything shown is FIXTURE: the committed contract card, the synthetic evidence file, and the
// staged listing and record of demo case "a". Stock photos stand in for the ad and the scan, so
// the pins here show layout only, not a match.
import cardHold from "../../../../fixtures/contracts/card_hold.json";
import listing from "../../../../fixtures/demo/a/listing.txt?raw";
import record from "../../../../fixtures/demo/a/property_record.json";
import type { Card } from "../contracts";
import { EVIDENCE_FIXTURE_A } from "../evidence/fixture";
import { pickSpots } from "../evidence/match";
import { Tag, photoFor } from "../ui";
import {
  AnnotatedAd,
  CaseResult,
  Ledger,
  PriceBar,
  ProofPair,
  RealListing,
  SaferTiles,
  type ProofPin,
} from ".";

const card = cardHold as Card;

const sample = photoFor({ source: "fixture", stock: "interior", seed: "story" });
const shot = { src: sample.src, alt: sample.alt, stamp: sample.stamp };

// Pins from the synthetic evidence file, picked the way the page picks them.
const pairs =
  EVIDENCE_FIXTURE_A.photos.find((p) => p.points?.sampled.length)?.points?.sampled ?? [];
const fixturePins: ProofPin[] = pickSpots(pairs, 3).map((i) => {
  const [ax, ay, sx, sy] = pairs[i]!;
  return { ax: ax * 100, ay: ay * 100, sx: sx * 100, sy: sy * 100 };
});
// Layout cases: a pin in the stamp's own corner, then pins in both left corners.
const lowPins: ProofPin[] = [
  { ax: 14, ay: 30, sx: 18, sy: 28 },
  { ax: 52, ay: 44, sx: 56, sy: 46 },
  { ax: 16, ay: 90, sx: 20, sy: 88 },
];
const bothPins: ProofPin[] = [...lowPins, { ax: 12, ay: 8, sx: 14, sy: 10 }];

// The staged listing's own rent and the synthetic record's range for its size.
const listed = Number(/\$([\d,]+)/.exec(listing)?.[1]?.replace(",", "") ?? NaN);
const plan = record.floor_plan_rents.find((p) => p.beds === 2);
const rentWords = /\$[\d,]+ a month/.exec(listing)?.[0] ?? null;
const link = /https?:\/\/\S+/.exec(listing)?.[0] ?? null;

export function Story() {
  return (
    <main className="shell">
      <div className="case-page" style={{ gap: 56 }}>
        <p className="case-head ui-mono">
          <span>CASE PIECES · SAMPLE VALUES</span>
          <Tag source="fixture" />
        </p>

        <section className="case-band ui-band ui-on-matte" data-story="proof">
          <ProofPair
            ad={shot}
            scan={shot}
            pins={fixturePins}
            kicker="PHOTO 1 OF 3"
            caption="Pins from the synthetic evidence file, on stock photos. Layout only."
          />
          <ProofPair
            ad={shot}
            scan={shot}
            pins={lowPins}
            caption="A pin in the lower left corner: the stamp moves to the top."
          />
          <ProofPair
            ad={shot}
            scan={shot}
            pins={bothPins}
            caption="Pins in both left corners: the stamp sits under the photo."
          />
        </section>

        {plan && Number.isFinite(listed) ? (
          <section data-story="price" style={{ display: "grid", gap: 32 }}>
            <h2>Price bar</h2>
            <PriceBar price={{ listed, min: plan.rent_min, max: plan.rent_max }} />
            <PriceBar
              price={{ listed: plan.rent_min - 10, min: plan.rent_min, max: plan.rent_max }}
            />
            <PriceBar
              price={{ listed: plan.rent_max + 40, min: plan.rent_min, max: plan.rent_max }}
            />
            <div style={{ maxWidth: 230 }}>
              <PriceBar price={{ listed, min: plan.rent_min, max: plan.rent_max }} />
            </div>
          </section>
        ) : null}

        <div className="case-body case-body-with-side" data-story="ad">
          <Ledger
            card={card}
            adSays={(_row, line) => (line.label === "Rent vs record" ? rentWords : null)}
            price={
              plan && Number.isFinite(listed)
                ? { listed, min: plan.rent_min, max: plan.rent_max }
                : null
            }
          />
          <div className="case-side" data-side="ad">
            <AnnotatedAd
              text={listing.trim()}
              origin="STAGED LISTING"
              marks={[
                ...(rentWords ? [{ phrase: rentWords, kind: "mismatch" as const }] : []),
                ...(link ? [{ phrase: link, kind: "warn" as const }] : []),
              ]}
            />
          </div>
        </div>

        <RealListing
          listing={{
            case_id: card.case_id,
            source: "fixture",
            which: "claimed",
            building_name: "Fixture Court",
            manager_company: record.manager_company,
            website_host: record.website_host,
            plans: plan ? [plan] : [],
            photos_in_scan: EVIDENCE_FIXTURE_A.photos.filter(
              (p) => p.status === "located_in_claimed",
            ).length,
            photos_total: EVIDENCE_FIXTURE_A.photos.length,
            ad_rent: Number.isFinite(listed) ? listed : null,
            ad_asks_irreversible: false,
            phone_is_office: "no",
            figures_shown: true,
            as_of: null,
          }}
        />

        <SaferTiles
          places={[1, 2, 3].map((n) => ({
            property_id: `fx-story-${n}`,
            floor_plan: plan?.name,
            price_text: "Sample tile. The words here come from the API.",
            source: "fixture" as const,
            handoff_url: `https://${record.website_host}/`,
            handoff_label: "The building's own site",
          }))}
        />

        <CaseResult
          card={card}
          inline
          proof={{ ad: shot, scan: shot, pins: [], caption: "Inline in the Home thread." }}
        />
      </div>
    </main>
  );
}

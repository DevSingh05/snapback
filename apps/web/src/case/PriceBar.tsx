// The clean price bar (locked Sat 14:57): a 1px track, the record's range as a 7px ink segment,
// the ad's price as a 17px mark in the mismatch colour, and two mono labels under it. No blocks.
// The labels sit at the two ends of one row with a gap between them, and wrap onto two lines
// when the row is too narrow, so they can never touch whatever the numbers are.
import "../ui/ui.css";
import "./case.css";
import { dollars, type PriceFigures } from "./model";

/** Where the mark and the segment sit on the track, in percent. */
export function priceScale({ listed, min, max }: PriceFigures) {
  const lo = Math.min(listed, min, max);
  const hi = Math.max(listed, min, max);
  const pad = Math.max((hi - lo) * 0.12, 1);
  const from = lo - pad;
  const span = hi + pad - from;
  const at = (n: number) => ((n - from) / span) * 100;
  const start = at(Math.min(min, max));
  return { mark: at(listed), start, width: Math.max(at(Math.max(min, max)) - start, 1) };
}

export function PriceBar({ price }: { price: PriceFigures }) {
  const lo = Math.min(price.min, price.max);
  const hi = Math.max(price.min, price.max);
  const { mark, start, width } = priceScale(price);
  const adLabel = `${dollars(price.listed)} in the ad`;
  const recordLabel =
    lo === hi ? `${dollars(lo)} on record` : `${dollars(lo)} to ${dollars(hi)} on record`;
  // The label for whichever sits further left comes first.
  const adFirst = price.listed <= lo;
  const ad = (
    <span className="case-price-label case-price-ad" data-testid="price-label-ad">
      {adLabel}
    </span>
  );
  const record = (
    <span className="case-price-label case-price-record" data-testid="price-label-record">
      {recordLabel}
    </span>
  );
  return (
    <div className="case-price" data-testid="case-price">
      <div className="case-price-track" role="img" aria-label={`${adLabel}; ${recordLabel}`}>
        <i className="case-price-range" style={{ left: `${start}%`, width: `${width}%` }} />
        <i className="case-price-mark" style={{ left: `${mark}%` }} />
      </div>
      <p className="case-price-labels ui-mono">
        {adFirst ? ad : record}
        {adFirst ? record : ad}
      </p>
      <p className="case-price-note">We can't tell you if it is offered, or at this price.</p>
    </div>
  );
}

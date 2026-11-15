// Which photo to show for a place or a case, by priority (design v3 1.4):
//   1 the renter's own upload                     stamp FROM THE AD
//   2 a real scan frame from the tour             stamp FROM THE 3D SCAN · LIVE
//   3 a kit photo served by the API at runtime    stamp FROM THE RECORD · LIVE
//   4 a licensed stock photo from src/assets      stamp SAMPLE PHOTO
//   5 the drawing                                 stamp DRAWN STAND-IN (src is null)
// Steps 2 and 3 are sponsor imagery: only ever a runtime address on the API, never imported,
// never in public/ or src/assets, never committed. On a FIXTURE run they are skipped, so a
// public host can never show them. Stock is never passed off as the listed home: the alt text
// describes what is in the frame and the stamp says Sample photo.
import type { DataSource } from "../contracts";
import type { StampKind } from "./Photo";
import { STOCK, type StockKind, type StockPhoto } from "./stock";

export interface PhotoSources {
  // 1. The renter's own upload (an object URL or a data URL made in this browser).
  upload?: string | null;
  // 2. A real scan frame, as an address on the API.
  scanFrame?: string | null;
  // 3. A kit photo, as an address on the API.
  kitPhoto?: string | null;
  // LIVE or FIXTURE for this place or case. Sponsor imagery shows on LIVE only.
  source?: DataSource;
  // 4. Which kind of stock photo fits, and a stable seed (a case or place id) so one place
  // always gets the same picture. `stock: null` skips stock and falls to the drawing.
  stock?: StockKind | null;
  seed?: string | number;
}

export interface ChosenPhoto {
  src: string | null;
  stamp: StampKind;
  alt: string;
  // Photographer credit for stock (one credit line per page); null otherwise.
  credit: string | null;
}

function pick(list: readonly StockPhoto[], seed: string | number | undefined): StockPhoto | null {
  if (list.length === 0) return null;
  const text = String(seed ?? "");
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return list[h % list.length]!;
}

export function photoFor(sources: PhotoSources, what = "the home"): ChosenPhoto {
  const { upload, scanFrame, kitPhoto, source = "fixture", stock = "interior", seed } = sources;
  if (upload)
    return { src: upload, stamp: "ad", alt: `Photo from the ad of ${what}`, credit: null };
  if (source === "live" && scanFrame)
    return { src: scanFrame, stamp: "scan", alt: `3D scan frame of ${what}`, credit: null };
  if (source === "live" && kitPhoto)
    return { src: kitPhoto, stamp: "record", alt: `Record photo of ${what}`, credit: null };
  const sample = stock ? pick(STOCK[stock], seed) : null;
  if (sample) return { src: sample.src, stamp: "sample", alt: sample.alt, credit: sample.credit };
  return { src: null, stamp: "drawn", alt: `Drawing standing in for ${what}`, credit: null };
}

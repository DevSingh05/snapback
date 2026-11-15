// Licensed stock photographs (Unsplash License), committed under src/assets and credited in
// src/assets/CREDITS.md. Shown only with the SAMPLE PHOTO stamp. The alt text says what is in
// the frame, never that it is the listed home or that it is in Houston.
import heroDusk from "../assets/hero-dusk-balconies.webp";
import sampleBuilding from "../assets/sample-building.webp";
import sampleLivingRoom from "../assets/sample-living-room.webp";
import sampleLounge from "../assets/sample-lounge.webp";

export type StockKind = "interior" | "exterior" | "hero-day" | "hero-dusk";

export interface StockPhoto {
  src: string;
  alt: string;
  credit: string;
}

export const STOCK: Record<StockKind, readonly StockPhoto[]> = {
  interior: [
    {
      src: sampleLivingRoom,
      alt: "A living room with a grey sofa",
      credit: "Minh Pham on Unsplash",
    },
    {
      src: sampleLounge,
      alt: "A living room with a pale green sofa",
      credit: "Collov Home Design on Unsplash",
    },
  ],
  exterior: [
    {
      src: sampleBuilding,
      alt: "An apartment building seen from below",
      credit: "Marlene Céline Nordvik on Unsplash",
    },
  ],
  "hero-day": [],
  "hero-dusk": [
    {
      src: heroDusk,
      alt: "Apartment balconies lit at dusk",
      credit: "Tobias Wilden on Unsplash",
    },
  ],
};

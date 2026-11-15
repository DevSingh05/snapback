// The proof pair for a case, read at run time. With the API: the case's evidence file (written by
// code), the ad's own photo and the scan frame it matched, all fetched with the read token in a
// header and shown through blob URLs, so no kit picture is ever bundled. Without the API
// (fixture mode): a licensed stock interior on both sides, stamped SAMPLE PHOTO, with no pins.
import { useEffect, useState } from "react";

import { apiBase, apiFetchRead, apiFetchReadWhenReady } from "../api";
import type { Card } from "../contracts";
import { pickSpots, pointsSentence } from "../evidence/match";
import { placeLine } from "../evidence/read";
import type { EvidenceFile, EvidencePhoto } from "../evidence/types";
import { useAdPhoto } from "../tour/useAdPhoto";
import { photoFor } from "../ui";
import type { ProofData, ProofPin } from "./model";

// Three pins read at a glance on a photo this size; the match view shows the rest.
const PINS = 3;

interface Found {
  file: EvidenceFile;
  photo: EvidencePhoto;
  placed: boolean;
  scan: string | null;
}

const isPlaced = (p: EvidencePhoto) => p.status === "located_in_claimed" && !p.bar_failed;

function pinsOf(photo: EvidencePhoto): ProofPin[] {
  const pairs = photo.points?.sampled ?? [];
  return pickSpots(pairs, PINS).map((i) => {
    const [ax, ay, sx, sy] = pairs[i]!;
    return { ax: ax * 100, ay: ay * 100, sx: sx * 100, sy: sy * 100 };
  });
}

function samplePair(card: Card): ProofData {
  const sample = photoFor({ source: "fixture", stock: "interior", seed: card.case_id });
  const shot = { src: sample.src, alt: sample.alt, stamp: sample.stamp };
  return {
    ad: shot,
    scan: shot,
    pins: [],
    kicker: null,
    caption:
      "Sample photos. On a live check the ad's photo sits here, beside the scan frame it matched.",
  };
}

const pair = (value: ProofData) => ({ value, waiting: false });

/** The proof pair, and whether the API is still checking (202) so the band can say so. */
export function useProofRead(card: Card): { value: ProofData | null; waiting: boolean } {
  const caseId = card.case_id;
  const live = Boolean(apiBase());
  // The card says when the case has no evidence file (a check with no photos): do not ask.
  const wanted = live && card.has_evidence !== false;
  const [found, setFound] = useState<Found | null>(null);
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    if (!wanted) return;
    const ctrl = new AbortController();
    let made: string | null = null;
    const base = `/cases/${encodeURIComponent(caseId)}/evidence`;
    (async () => {
      try {
        const res = await apiFetchReadWhenReady(base, caseId, { signal: ctrl.signal }, (w) => {
          if (!ctrl.signal.aborted && w) setWaiting(true);
        });
        if (!ctrl.signal.aborted) setWaiting(false);
        if (!res?.ok || res.status === 202) return;
        const file = (await res.json()) as EvidenceFile;
        const photo = file.photos?.find(isPlaced) ?? file.photos?.[0];
        if (!photo) return;
        const placed = isPlaced(photo);
        if (placed) {
          const img = await apiFetchRead(
            `${base}/${encodeURIComponent(photo.alias)}/scan.jpg`,
            caseId,
            {
              signal: ctrl.signal,
            },
          );
          if (img?.ok && (img.headers.get("content-type") ?? "").startsWith("image/"))
            made = URL.createObjectURL(await img.blob());
        }
        if (!ctrl.signal.aborted) setFound({ file, photo, placed, scan: made });
      } catch {
        // No evidence to show: the band stands without the pair.
      }
    })();
    return () => {
      ctrl.abort();
      if (made) URL.revokeObjectURL?.(made);
    };
  }, [caseId, wanted]);

  const adUrl = useAdPhoto(found ? caseId : null, found?.photo.alias);

  if (!live) return { value: samplePair(card), waiting: false };
  // A pair needs the renter's own photo; without it nothing is shown rather than a stand-in.
  if (!found || !adUrl) return { value: null, waiting };
  const { file, photo, placed, scan } = found;
  const n = file.photos.indexOf(photo) + 1;
  const ad = { src: adUrl, alt: `Photo ${n} from the ad`, stamp: "ad" as const };
  const kicker = `PHOTO ${n} OF ${file.photos.length}`;
  if (placed && scan) {
    return pair({
      ad,
      scan: { src: scan, alt: "The 3D scan frame this photo matched", stamp: "scan" },
      pins: pinsOf(photo),
      kicker,
      caption: [placeLine(photo), pointsSentence(photo, file.bars)].filter(Boolean).join(". "),
    });
  }
  const building = photoFor({ source: "fixture", stock: "exterior", seed: caseId });
  return pair({
    ad,
    scan: { src: building.src, alt: building.alt, stamp: building.stamp },
    pins: [],
    kicker,
    caption: placeLine(photo),
  });
}

export function useProof(card: Card): ProofData | null {
  return useProofRead(card).value;
}

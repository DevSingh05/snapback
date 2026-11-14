"""The synthetic ad corpus: its shape and its loader. Made by `generate.py`, never real."""

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "forensics"
ADS_PATH = FIXTURE_DIR / "ads.json"
TRUTH_PATH = FIXTURE_DIR / "ground_truth.json"

# Every phone in the corpus is a 555 number: fictional by convention, never a real subscriber.
PHONE_RE = re.compile(r"^555-\d{4}$")
# A perceptual-hash-like photo id: 64 bits as 16 hex digits.
PHOTO_RE = re.compile(r"^ph-[0-9a-f]{16}$")


class Ad(BaseModel):
    id: int
    posted_at: str  # ISO date
    hood: str  # a made-up neighbourhood of a made-up city
    beds: int
    rent: int
    title: str
    text: str
    phone: str
    photos: list[str] = Field(default_factory=list)  # perceptual-hash-like ids
    synthetic: bool = True


class Corpus(BaseModel):
    label: str
    seed: int
    ads: list[Ad]

    def by_id(self) -> dict[int, Ad]:
        return {ad.id: ad for ad in self.ads}


def load_corpus(path: Path = ADS_PATH) -> Corpus:
    return Corpus.model_validate(json.loads(path.read_text()))


def load_truth(path: Path = TRUTH_PATH) -> dict[str, list[int]]:
    """Ring name -> ad ids. Used by `evaluate` only; the pipeline never reads it."""
    data = json.loads(path.read_text())
    return {name: [int(i) for i in ids] for name, ids in data["rings"].items()}

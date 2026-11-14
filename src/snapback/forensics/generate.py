"""Seeded generator for the SYNTHETIC rental-ad corpus (about 300 ads, a made-up city).

    uv run python -m snapback.forensics.generate [--seed N] [--out DIR]

Same seed, same bytes. Most ads are honest. Four rings are seeded:

- A, photo recycler: a small pool of photo sets reused (re-cropped, so the perceptual-hash-like
  ids differ by a few bits), seven rotating 555 numbers, payment-first wording in many forms.
- B, copied listings: photos lifted from earlier honest ads and posted under new contact details.
- C, wording ring: fresh photos every time; linked only by reworded payment-first text and
  phone numbers that each serve two or three ads.
- D, one number per ad: eight ads, eight numbers, two recycled photo sets.

Honest look-alikes are in the mix on purpose, so a detector that only counts shared words or
shared photos is punished: property managers who reuse one number and one template, owners who
relist the same unit with the same photos, and honest ads that talk about deposits and Zelle
after move-in. Everything is labelled SYNTHETIC; there is no real address, number or photo.
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from snapback.forensics.corpus import FIXTURE_DIR

DEFAULT_SEED = 20261114
LABEL = (
    "SYNTHETIC: generated rental ads for the forensics demo. Not real people, places or numbers."
)

HOODS = [
    "Alder Flats",
    "Kestrel Row",
    "Millrace",
    "Oakbend",
    "Pelham Green",
    "Quarry Hill",
    "Saltmarsh",
    "Tern Point",
    "Westering",
    "Ashgrove",
]
STREETS = ["Linden", "Harrow", "Cobble", "Fenwick", "Juniper", "Marlow", "Sparrow", "Tilbury"]
FEATURES = [
    "hardwood floors",
    "a bright kitchen",
    "in-unit laundry",
    "a small balcony",
    "new windows",
    "a quiet courtyard",
    "off-street parking",
    "a renovated bath",
    "lots of closet space",
    "high ceilings",
]
HONEST_OPEN = [
    "Welcome to this {beds}-bedroom home in {hood} with {f1} and {f2}.",
    "Sunny {beds}-bedroom on {street} Street, {hood}. Features {f1} and {f2}.",
    "{beds} bed apartment near the {hood} market: {f1}, {f2}, and a short walk to the bus.",
    "Well kept {beds}-bedroom in {hood}. You will love {f1} and {f2}.",
]
HONEST_TERMS = [
    "Showings are by appointment. Deposit of one month is due at lease signing, after you tour.",
    "Come see it first; the application fee is paid through our online portal.",
    "First month's rent is collected on move-in day. Tour any weekday.",
    "Tenants may pay monthly rent by Zelle or check once they have moved in.",
    "We never ask for money before you have seen the unit. No wire, no gift cards.",
    "Pets negotiable. Water included. Lease terms are twelve months.",
    "Apply on our website. The security deposit is due once approved, after a walk-through.",
    "Rent covers water and trash. Deposit is collected at the signing table.",
]
MANAGER_TEMPLATE = (
    "Managed by Harbor Row Property Group. {beds}-bedroom in {hood}, {f1}. "
    "Tour with our leasing office. Deposit due at lease signing."
)

# Payment-first wording. The first three are the shapes the existing money rules know; the
# rest say the same thing in other words, which a keyword or regex search does not catch.
ASK_PLAIN = [
    "The security deposit and first month's rent are due before move-in.",
    "You will pay the deposit before moving in, then I post the keys to you.",
    "Zelle the deposit to hold the unit, I cannot show it until it arrives.",
]
ASK_REWORDED = [
    "Kindly remit the holding amount ahead of receiving the keys.",
    "A reservation sum must reach me before the keys are released; the unit is yours.",
    "Send the reservation payment first and I will mail the keys and the lease to you.",
    "To secure it, transfer the first month up front; viewing happens after the keys arrive.",
    "Upfront reservation funds are needed prior to key handover.",
    "Forward the booking amount today and the apartment is reserved in your name.",
    "Your booking amount has to be paid in advance of collecting the keys.",
]
PRETEXT = [
    "I am out of town for work, so I can't show it myself.",
    "The owner is out of town and the unit is under new management.",
    "I am overseas on a posting and cannot meet in person.",
    "",
]
SIGNOFFS = ["Blessings, the Owner's Office.", "Warm regards from the Owner's Office.", ""]


def _hash(rng: random.Random) -> str:
    return f"ph-{rng.getrandbits(64):016x}"


def _recrop(rng: random.Random, photo: str, max_bits: int = 3) -> str:
    """A re-cropped or re-compressed copy: the same picture, a few bits different."""
    value = int(photo[3:], 16)
    for bit in rng.sample(range(64), rng.randint(0, max_bits)):
        value ^= 1 << bit
    return f"ph-{value:016x}"


class _Phones:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.used: set[str] = set()

    def new(self) -> str:
        while True:
            number = f"555-{self.rng.randint(1000, 9999):04d}"
            if number not in self.used:
                self.used.add(number)
                return number


def _fill(rng: random.Random, beds: int, hood: str) -> dict[str, object]:
    f1, f2 = rng.sample(FEATURES, 2)
    return {"beds": beds, "hood": hood, "f1": f1, "f2": f2, "street": rng.choice(STREETS)}


def _honest_text(rng: random.Random, beds: int, hood: str) -> str:
    opener = rng.choice(HONEST_OPEN).format(**_fill(rng, beds, hood))
    return f"{opener} {rng.choice(HONEST_TERMS)}"


def _ring_text(
    rng: random.Random, beds: int, hood: str, ask: str, *, pretext: bool, base: str | None
) -> str:
    body = base or rng.choice(HONEST_OPEN).format(**_fill(rng, beds, hood))
    parts = [body, ask]
    if pretext:
        parts.append(rng.choice([p for p in PRETEXT if p]))
    parts.append(rng.choice(SIGNOFFS))
    return " ".join(p for p in parts if p)


def _rent(rng: random.Random, beds: int, low: bool = False) -> int:
    base = 700 + 330 * beds + rng.randint(-60, 90)
    return int(base * (0.62 if low else 1.0) // 5 * 5)


def _day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate(seed: int = DEFAULT_SEED) -> tuple[dict[str, object], dict[str, object]]:
    rng = random.Random(seed)
    phones = _Phones(rng)
    rows: list[dict[str, object]] = []  # ad dicts without ids yet
    ring_of: dict[int, str] = {}  # index in rows -> ring name

    def add(day: date, beds: int, hood: str, text: str, rent: int, phone: str, photos: list[str]):
        rows.append(
            {
                "posted_at": day.isoformat(),
                "hood": hood,
                "beds": beds,
                "rent": rent,
                "title": f"{beds} BR in {hood}",
                "text": text,
                "phone": phone,
                "photos": photos,
                "synthetic": True,
            }
        )
        return len(rows) - 1

    year_start, year_end = date(2026, 1, 5), date(2026, 6, 28)

    # ---- honest ads ------------------------------------------------------------------------
    for _ in range(200):  # individual owners, one number and one photo set each
        beds = rng.randint(1, 4)
        hood = rng.choice(HOODS)
        add(
            _day(rng, year_start, year_end),
            beds,
            hood,
            _honest_text(rng, beds, hood),
            _rent(rng, beds),
            phones.new(),
            [_hash(rng) for _ in range(rng.randint(4, 7))],
        )
    for _ in range(5):  # property managers: one number, one template, several units
        number = phones.new()
        for _ in range(rng.randint(5, 8)):
            beds = rng.randint(1, 3)
            hood = rng.choice(HOODS[:4])
            text = MANAGER_TEMPLATE.format(**_fill(rng, beds, hood))
            add(
                _day(rng, year_start, year_end),
                beds,
                hood,
                text,
                _rent(rng, beds),
                number,
                [_hash(rng) for _ in range(5)],
            )
    honest_count = len(rows)
    for _ in range(12):  # honest relists: same owner, same number, same photos, later date
        src = rows[rng.randrange(honest_count)]
        later = date.fromisoformat(str(src["posted_at"])) + timedelta(days=rng.randint(25, 70))
        add(
            min(later, date(2026, 6, 29)),
            int(src["beds"]),
            str(src["hood"]),
            str(src["text"]),
            int(src["rent"]) - 25,
            str(src["phone"]),
            list(src["photos"]),  # type: ignore[arg-type]
        )
    honest_total = len(rows)

    # ---- ring A: photo recycler -------------------------------------------------------------
    pool = [[_hash(rng) for _ in range(5)] for _ in range(6)]
    a_phones = [phones.new() for _ in range(7)]
    for i in range(22):
        beds = rng.randint(1, 3)
        hood = rng.choice(HOODS)
        photos = [_recrop(rng, p) for p in rng.choice(pool)]
        ask = rng.choice(ASK_PLAIN if rng.random() < 0.4 else ASK_REWORDED)
        day = date(2026, 2, 3) + timedelta(days=int(i * 76 / 21) + rng.randint(0, 2))
        idx = add(
            day,
            beds,
            hood,
            _ring_text(rng, beds, hood, ask, pretext=rng.random() < 0.5, base=None),
            _rent(rng, beds, low=True),
            a_phones[(i * 7 // 22 + rng.randint(0, 1)) % 7],
            photos,
        )
        ring_of[idx] = "A"

    # ---- ring B: honest photos copied under new contact details ----------------------------
    sources = rng.sample(range(honest_total), 15)
    b_phones = [phones.new() for _ in range(6)]
    for i, src_idx in enumerate(sources):
        src = rows[src_idx]
        reworded_ask = rng.random() < 0.75
        ask = rng.choice(ASK_REWORDED) if reworded_ask else rng.choice(ASK_PLAIN)
        if i in (3, 9):  # two copies keep quiet about money: only the evidence links them
            ask = ""
        day = max(
            date(2026, 3, 10) + timedelta(days=i * 3 + rng.randint(0, 2)),
            date.fromisoformat(str(src["posted_at"])) + timedelta(days=5),
        )
        idx = add(
            min(day, date(2026, 6, 29)),
            int(src["beds"]),
            str(src["hood"]),
            _ring_text(
                rng, int(src["beds"]), str(src["hood"]), ask, pretext=rng.random() < 0.4, base=None
            ),
            int(src["rent"]) - 250,
            b_phones[i * 6 // 15],
            [_recrop(rng, p, 2) for p in src["photos"]],  # type: ignore[union-attr]
        )
        ring_of[idx] = "B"

    # ---- ring C: reworded text, chained numbers, fresh photos ------------------------------
    c_phones = [phones.new() for _ in range(5)]
    c_voice = rng.sample(ASK_REWORDED, 4)
    for i in range(12):
        beds = rng.randint(1, 3)
        hood = rng.choice(HOODS)
        idx = add(
            date(2026, 4, 6) + timedelta(days=i * 5 + rng.randint(0, 3)),
            beds,
            hood,
            _ring_text(rng, beds, hood, rng.choice(c_voice), pretext=True, base=None),
            _rent(rng, beds, low=True),
            c_phones[i // 3 + (1 if i % 3 == 2 and i // 3 < 4 else 0)],
            [_hash(rng) for _ in range(rng.randint(4, 6))],
        )
        ring_of[idx] = "C"

    # ---- ring D: a new number for every ad, two recycled photo sets ------------------------
    d_pool = [[_hash(rng) for _ in range(5)] for _ in range(2)]
    for i in range(8):
        beds = rng.randint(1, 3)
        hood = rng.choice(HOODS)
        idx = add(
            date(2026, 5, 18) + timedelta(days=i * 4 + rng.randint(0, 2)),
            beds,
            hood,
            _ring_text(
                rng,
                beds,
                hood,
                rng.choice(ASK_REWORDED + ASK_PLAIN[:1]),
                pretext=rng.random() < 0.6,
                base=None,
            ),
            _rent(rng, beds, low=True),
            phones.new(),
            [_recrop(rng, p) for p in d_pool[i % 2]],
        )
        ring_of[idx] = "D"

    # ---- ids in posting order ---------------------------------------------------------------
    order = sorted(range(len(rows)), key=lambda k: (str(rows[k]["posted_at"]), k))
    new_id = {old: n + 1 for n, old in enumerate(order)}
    ads = []
    for old in order:
        ads.append({"id": new_id[old], **rows[old]})
    rings: dict[str, list[int]] = {}
    for old, name in ring_of.items():
        rings.setdefault(name, []).append(new_id[old])
    sources_ids = sorted(new_id[s] for s in sources)
    corpus = {"label": LABEL, "seed": seed, "ads": ads}
    truth = {
        "label": LABEL,
        "seed": seed,
        "rings": {k: sorted(v) for k, v in sorted(rings.items())},
        "ring_b_source_ads": sources_ids,  # honest ads whose photos ring B copied
    }
    return corpus, truth


def write(out: Path, seed: int = DEFAULT_SEED) -> None:
    corpus, truth = generate(seed)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ads.json").write_text(json.dumps(corpus, indent=1, sort_keys=True) + "\n")
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()
    write(args.out, args.seed)
    print(f"wrote {args.out}/ads.json and ground_truth.json (seed {args.seed})")

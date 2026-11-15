"""Seeded generator for a SYNTHETIC stream of rental ads: about 3,000 ads over 90 days.

    uv run python -m snapback.forensics.stream [--seed N] [--out DIR]

Same seed, same bytes. It is the 300-ad corpus (`generate.py`) grown along the time axis, so the
ring finder can be run day by day and asked how soon it links a ring. Nothing here comes from
the CoStar kit: a made-up city, 555 numbers, `.example` sites, hash-like photo ids.

Ten rings by default (8 to 12), each active for a few weeks, each changing how it works as it goes:

- phones rotate: a number serves two to four ads, then is dropped for a new one;
- sites move: no link at first, then a pay-here site, then lookalikes of an honest manager's site;
- photos are reused, re-cropped a little at first and more heavily later (a mirrored or heavily
  cropped copy keeps few of its bits), with some fresh sets mixed in;
- the wording is paraphrased more with each phase.

Hard honest negatives are in the stream on purpose:

- one management company listing many buildings from one number, one template and its own site;
- a second manager with two numbers and a house style;
- owners who relist the same unit with the same photos;
- honest ads that mention a deposit, Zelle or a fee the way real leases do.

The truth file says which ads belong to which ring and, per ring, the day each phase began.
`pipeline.analyze` never reads it.
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from snapback.forensics.generate import (
    HONEST_OPEN,
    HOODS,
    MANAGER_TEMPLATE,
    PRETEXT,
    VOICES,
    _fill,
    _hash,
    _honest_text,
    _Phones,
    _recrop,
    _rent,
    _reword,
)

DEFAULT_SEED = 20261115
START = date(2026, 8, 17)
DAYS = 90
N_RINGS = 10
HONEST_PER_DAY = (26, 34)  # about 2,700 honest ads over the 90 days
LABEL = (
    "SYNTHETIC: a generated 90-day stream of rental ads for the forensics demo. "
    "Not real people, places, numbers or sites."
)
MANAGER_SITE = "harborrow.example"
SECOND_MANAGER = (
    "Listed by Tidewater Residential. {beds}-bedroom in {hood} with {f1}. "
    "Call our leasing desk for a tour; the application is on our site."
)
SECOND_SITE = "tidewater-residential.example"
PHASES = ("early", "middle", "late")
# How far a reused photo drifts from its original, per phase: a light re-crop, a heavier crop,
# then a mirrored or re-framed copy that keeps few of its bits.
CROP_BITS = {"early": 3, "middle": 6, "late": 14}
EXTRA_ASKS = [
    "The first month and the deposit go through before any viewing is arranged.",
    "A refundable holding payment locks the unit; the tour is scheduled once it clears.",
    "Send the move-in funds and the key courier is booked the same day.",
    "Payment secures your place in line ahead of the other applicants.",
]


def _lookalike(rng: random.Random, host: str) -> str:
    """A site that imitates `host`: a doubled letter, an added word or a swapped ending."""
    name, _, rest = host.partition(".")
    kind = rng.randrange(3)
    if kind == 0:
        at = rng.randrange(len(name))
        return f"{name[:at]}{name[at]}{name[at:]}.{rest}"
    if kind == 1:
        return f"{name}-{rng.choice(['leasing', 'apply', 'rentals', 'office'])}.{rest}"
    return f"{name}{rng.choice(['homes', 'living', 'now'])}.{rest}"


def _ring_plan(rng: random.Random, n_rings: int) -> list[dict[str, object]]:
    plans = []
    kinds = ["photos", "sites", "wording", "copier"]
    rng.shuffle(kinds)  # every way of working appears; the order depends on the seed
    for k in range(n_rings):
        length = rng.randint(18, 40)  # days the ring is active
        start = rng.randint(2, DAYS - length - 2)
        plans.append(
            {
                "name": f"R{k + 1:02d}",
                "start": start,
                "length": length,
                "n_ads": rng.randint(16, 44),
                "voice": rng.choice(sorted(VOICES)),
                # what the ring leans on: every ring rotates phones; these differ in the rest
                "style": kinds[k % len(kinds)],
            }
        )
    return plans


def generate_stream(
    seed: int = DEFAULT_SEED, n_rings: int = N_RINGS
) -> tuple[dict[str, object], dict[str, object]]:
    """The stream and its ground truth, as plain dicts shaped like `generate.generate`'s."""
    if not 8 <= n_rings <= 12:
        raise ValueError("the stream plants 8 to 12 rings")
    rng = random.Random(seed)
    phones = _Phones(rng)
    rows: list[dict[str, object]] = []
    ring_of: dict[int, str] = {}
    phase_of: dict[int, str] = {}

    def add(
        day: int, beds: int, hood: str, text: str, rent: int, phone: str, photos: list[str]
    ) -> int:
        rows.append(
            {
                "posted_at": (START + timedelta(days=day)).isoformat(),
                "hood": hood,
                "beds": beds,
                "rent": rent,
                "title": f"{beds} bed in {hood}",
                "text": text,
                "phone": phone,
                "photos": photos,
                "synthetic": True,
            }
        )
        return len(rows) - 1

    def fresh_photos() -> list[str]:
        return [_hash(rng) for _ in range(rng.randint(3, 5))]

    # ---- honest background, with the hard negatives ----------------------------------------
    manager_phone = phones.new()
    second_phones = [phones.new(), phones.new()]
    relisters: list[tuple[int, str, list[str], str, int]] = []  # beds, hood, photos, phone, rent
    honest_photo_sets: list[tuple[int, list[str]]] = []  # (day, photos) a copier ring can lift
    for day in range(DAYS):
        for _ in range(rng.randint(*HONEST_PER_DAY)):
            beds, hood = rng.randint(0, 4), rng.choice(HOODS)
            roll = rng.random()
            if roll < 0.045:  # the big manager: one number, one template, many buildings
                text = MANAGER_TEMPLATE.format(**_fill(rng, beds, hood))
                text += f" Apply at https://{MANAGER_SITE}/."
                add(day, beds, hood, text, _rent(rng, beds), manager_phone, fresh_photos())
            elif roll < 0.065:  # the second manager: two numbers, a house style
                text = SECOND_MANAGER.format(**_fill(rng, beds, hood))
                text += f" See https://{SECOND_SITE}/."
                add(
                    day,
                    beds,
                    hood,
                    text,
                    _rent(rng, beds),
                    rng.choice(second_phones),
                    fresh_photos(),
                )
            elif roll < 0.085 and relisters:  # an owner relists the same unit
                beds, hood, photos, phone, rent = rng.choice(relisters)
                add(
                    day,
                    beds,
                    hood,
                    _honest_text(rng, beds, hood),
                    rent + rng.choice([0, -25, 25]),
                    phone,
                    photos,
                )
            else:
                photos, phone, rent = fresh_photos(), phones.new(), _rent(rng, beds)
                add(day, beds, hood, _honest_text(rng, beds, hood), rent, phone, photos)
                honest_photo_sets.append((day, photos))
                if rng.random() < 0.02:
                    relisters.append((beds, hood, photos, phone, rent))

    # ---- the rings ---------------------------------------------------------------------------
    plans = _ring_plan(rng, n_rings)
    phase_days: dict[str, dict[str, str]] = {}
    pools: dict[str, list[list[str]]] = {}  # the originals each ring re-crops (truth only)
    for plan in plans:
        name, start, length = str(plan["name"]), int(plan["start"]), int(plan["length"])  # type: ignore[call-overload]
        n_ads, voice, style = int(plan["n_ads"]), str(plan["voice"]), str(plan["style"])  # type: ignore[call-overload]
        pool = [fresh_photos() for _ in range(rng.randint(2, 4))]
        pools[name] = pool
        pay_site = f"{rng.choice(['secure', 'fast', 'easy'])}-deposit-{rng.randint(10, 99)}.example"
        phone, served, limit = phones.new(), 0, rng.randint(2, 4)
        base_open = rng.choice(HONEST_OPEN)
        asks = [*VOICES[voice], *rng.sample(EXTRA_ASKS, 2)]
        days = sorted(start + rng.randint(0, length) for _ in range(n_ads))
        phase_days[name] = {}
        for i, day in enumerate(days):
            phase = PHASES[min(2, 3 * i // n_ads)]
            phase_days[name].setdefault(phase, (START + timedelta(days=day)).isoformat())
            if served >= limit:  # this number is burned; rotate
                phone, served, limit = phones.new(), 0, rng.randint(2, 4)
            served += 1
            beds, hood = rng.randint(1, 3), rng.choice(HOODS)

            # photos: reuse from the pool with drift, lift from an honest ad, or post fresh ones
            if style == "copier":
                earlier = [p for d, p in honest_photo_sets if d < day] or pool
                photos = [_recrop(rng, p, CROP_BITS[phase]) for p in rng.choice(earlier)]
            elif style == "wording" or (style == "sites" and rng.random() < 0.5):
                photos = fresh_photos()
            else:
                photos = [_recrop(rng, p, CROP_BITS[phase]) for p in rng.choice(pool)]
                if phase == "late" and rng.random() < 0.3:
                    photos = fresh_photos()

            # wording: the operator's own opener, paraphrased more as time goes on
            ask = rng.choice(asks)
            for _ in range(PHASES.index(phase) + 1):
                ask = _reword(rng, ask)
            opener = base_open if style != "copier" else rng.choice(HONEST_OPEN)
            parts = [opener.format(**_fill(rng, beds, hood)), ask]
            if rng.random() < 0.6:
                parts.append(rng.choice([p for p in PRETEXT if p]))

            # sites: none, then a pay-here site, then lookalikes of the honest manager's
            if phase == "middle" and style in ("sites", "wording", "photos"):
                parts.append(f"Reserve at https://{pay_site}/.")
            elif phase == "late" and style in ("sites", "wording", "copier"):
                parts.append(f"Apply at https://{_lookalike(rng, MANAGER_SITE)}/.")

            idx = add(day, beds, hood, " ".join(parts), _rent(rng, beds, low=True), phone, photos)
            ring_of[idx], phase_of[idx] = name, phase

    # ---- ids in posting order ----------------------------------------------------------------
    order = sorted(range(len(rows)), key=lambda k: (str(rows[k]["posted_at"]), k))
    new_id = {old: n + 1 for n, old in enumerate(order)}
    ads = [{"id": new_id[old], **rows[old]} for old in order]
    rings: dict[str, list[int]] = {}
    for old, name in ring_of.items():
        rings.setdefault(name, []).append(new_id[old])
    corpus = {"label": LABEL, "seed": seed, "ads": ads}
    truth = {
        "label": LABEL,
        "seed": seed,
        "days": DAYS,
        "start": START.isoformat(),
        "rings": {k: sorted(v) for k, v in sorted(rings.items())},
        "styles": {str(p["name"]): str(p["style"]) for p in plans},
        "phase_started": phase_days,
        "photo_pools": pools,
        "phase_of_ad": {str(new_id[old]): phase for old, phase in sorted(phase_of.items())},
        "hard_negatives": {
            "manager_phone_ads": sum(1 for r in rows if r["phone"] == manager_phone),
            "second_manager_ads": sum(1 for r in rows if r["phone"] in second_phones),
            "relisted_units": len(relisters),
        },
    }
    return corpus, truth


def write(out: Path, seed: int = DEFAULT_SEED, n_rings: int = N_RINGS) -> None:
    corpus, truth = generate_stream(seed, n_rings)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stream_ads.json").write_text(json.dumps(corpus, indent=1, sort_keys=True) + "\n")
    (out / "stream_truth.json").write_text(json.dumps(truth, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rings", type=int, default=N_RINGS)
    parser.add_argument("--out", type=Path, default=Path("data/forensics"))
    args = parser.parse_args()
    write(args.out, args.seed, args.rings)
    made, _ = generate_stream(args.seed, args.rings)
    n_ads = len(made["ads"])  # type: ignore[arg-type]
    print(f"SYNTHETIC stream: {n_ads} ads over {DAYS} days, {args.rings} rings, seed {args.seed}")
    print(f"wrote {args.out}/stream_ads.json and stream_truth.json")

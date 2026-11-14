"""Ad vs record: what the ad claims, held against what CoStar's record says (information only).

Rules this module keeps, each pinned by a test:

- A mismatch is a note only when the record clearly says otherwise. When the record has nothing
  on a claim, there is no note at all (never "not on record" filler).
- At most `MAX_NOTES` notes, pretext first, then the home's own claims. At most one of them is
  a quiet confirmation, and only when there is room.
- A note is facts (a key, the claim, record words, a year). The words come from the string
  table, so no language model and no kit text reaches a card.
- Nothing here reads a verdict or changes one. A note never accuses anyone: it says what the ad
  says and what the record shows, "as of CoStar's last research".
"""

from collections.abc import Callable
from datetime import date, timedelta

from snapback.agent.intake.claims import PRETEXT, AdClaims, ClaimKind
from snapback.contracts import AdNote, PropertyRecord

MAX_NOTES = 3
RECENT = timedelta(days=365)
# A photo's labels name a floor often by chance (one bedroom shot): need this many to speak.
MIN_FLOOR_PHOTOS = 2
BATHS_SLACK = 0.5  # "2.5 bath" against 2 full baths on record is the same home
SQFT_SLACK = 0.10

_FLOOR_OF = {
    ClaimKind.FLOOR_WOOD: "wood",
    ClaimKind.FLOOR_CARPET: "carpet",
    ClaimKind.FLOOR_TILE: "tile",
    ClaimKind.FLOOR_LAMINATE: "laminate",
}

Rule = Callable[[AdClaims, PropertyRecord, date], list[AdNote]]


def _note(key: str, claim: ClaimKind, **fields: object) -> AdNote:
    return AdNote(key=key, claim=claim.value, pretext=claim in PRETEXT, **fields)  # type: ignore[arg-type]


def _has_office(record: PropertyRecord) -> bool:
    return bool(record.site_phone_hash or record.website_host or record.manager_company)


# --- pretext ----------------------------------------------------------------------------------


def _manager(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    if ClaimKind.NEW_MANAGEMENT not in claims.kinds() or record.manager_since is None:
        return []
    claim = ClaimKind.NEW_MANAGEMENT
    year = record.manager_since.year
    if today - record.manager_since <= RECENT:
        return [_note("manager_new", claim, matches=True, year=year)]
    return [_note("manager_same", claim, year=year)]


def _sale(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    # "just sold" and "new ownership" are the same finding; the first one the ad made is quoted.
    kinds = claims.kinds()
    claim = next((c for c in (ClaimKind.JUST_SOLD, ClaimKind.NEW_OWNERSHIP) if c in kinds), None)
    if claim is None or not record.sale_history_known:
        return []
    if record.last_sale is None:
        return [_note("sale_none", claim)]
    year = record.last_sale.year
    if today - record.last_sale <= RECENT:
        return [_note("sale_recent", claim, matches=True, year=year)]
    return [_note("sale_older", claim, year=year)]


def _office(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    kinds = claims.kinds()
    claim = next((c for c in (ClaimKind.CANT_SHOW, ClaimKind.OWNER_AWAY) if c in kinds), None)
    if claim is None or not _has_office(record):
        return []
    return [_note("office_listed", claim)]


# --- the home's own claims --------------------------------------------------------------------


def _floors(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    photos = record.floors_photos if record.floor_photo_count >= MIN_FLOOR_PHOTOS else []
    seen = {*photos, *record.floors_listing, *record.floors_photos}
    out = []
    for claim in claims.claims:
        kind = _FLOOR_OF.get(claim.kind)
        if kind is None:
            continue
        if kind in seen:
            out.append(_note("floor_match", claim.kind, matches=True, record=[kind]))
        elif photos:
            out.append(_note("floor_photos", claim.kind, record=list(photos)))
        elif record.floors_listing:
            out.append(_note("floor_listing", claim.kind, record=list(record.floors_listing)))
    return out


def _washer(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    if ClaimKind.WASHER_DRYER not in claims.kinds() or not record.laundry_listing:
        return []
    if "machine" in record.laundry_listing:
        return [_note("wd_match", ClaimKind.WASHER_DRYER, matches=True)]
    return [_note("wd_listing", ClaimKind.WASHER_DRYER, record=list(record.laundry_listing))]


def _pool(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    if ClaimKind.POOL not in claims.kinds() or record.pool_on_record is None:
        return []
    if record.pool_on_record:
        return [_note("pool_match", ClaimKind.POOL, matches=True)]
    return [_note("pool_none", ClaimKind.POOL)]


def _parking(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    # Only zero spaces contradicts the ad: "garage" against two spaces on record is not clear.
    if ClaimKind.GARAGE not in claims.kinds():
        return []
    if record.parking_spaces is not None:
        if record.parking_spaces == 0:
            return [_note("parking_none", ClaimKind.GARAGE)]
        return [_note("parking_match", ClaimKind.GARAGE, matches=True)]
    # A building's record gives a ratio (spaces per unit); 0 reads as unknown, so a ratio
    # can confirm parking and never contradict it.
    if record.parking_ratio is not None:
        return [
            _note(
                "parking_ratio_match",
                ClaimKind.GARAGE,
                matches=True,
                record_value=f"{record.parking_ratio:.1f}",
            )
        ]
    return []


def _yard(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    # The record never says "no yard", so a yard can be confirmed and never contradicted.
    if ClaimKind.YARD in claims.kinds() and record.yard_on_record:
        return [_note("yard_match", ClaimKind.YARD, matches=True)]
    return []


def _pets(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    if ClaimKind.PETS not in claims.kinds() or record.pets_ok is None:
        return []
    if record.pets_ok:
        return [_note("pets_match", ClaimKind.PETS, matches=True)]
    return [_note("pets_no", ClaimKind.PETS)]


def _number(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:g}"


def _range(low: float, high: float) -> str:
    return _number(low) if low == high else f"{_number(low)} to {_number(high)}"


def _counted(
    claims: AdClaims,
    kind: ClaimKind,
    span: tuple[float, float] | None,
    key: str,
    slack: Callable[[float, float], tuple[float, float]],
) -> list[AdNote]:
    claim = next((c for c in claims.claims if c.kind is kind), None)
    if claim is None or claim.value is None or span is None:
        return []
    low, high = slack(*span)
    if low <= claim.value <= high:
        return [_note(f"{key}_match", kind, matches=True)]
    return [
        _note(
            f"{key}_differ",
            kind,
            ad_value=_number(claim.value),
            record_value=_range(*span),
        )
    ]


def _beds(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    return _counted(claims, ClaimKind.BEDS, record.beds_range, "beds", lambda a, b: (a, b))


def _baths(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    return _counted(
        claims,
        ClaimKind.BATHS,
        record.baths_range,
        "baths",
        lambda a, b: (a - BATHS_SLACK, b + BATHS_SLACK),
    )


def _sqft(claims: AdClaims, record: PropertyRecord, today: date) -> list[AdNote]:
    return _counted(
        claims,
        ClaimKind.SQFT,
        record.sqft_range,
        "sqft",
        lambda a, b: (a * (1 - SQFT_SLACK), b * (1 + SQFT_SLACK)),
    )


# Pretext first: it is what the renter most needs to see. Then the home's own claims.
RULES: tuple[Rule, ...] = (
    _manager,
    _sale,
    _office,
    _floors,
    _washer,
    _pool,
    _parking,
    _pets,
    _beds,
    _baths,
    _sqft,
    _yard,
)


EXTERIOR = (ClaimKind.POOL, ClaimKind.GARAGE, ClaimKind.YARD)


def compare_ad_to_record(
    claims: AdClaims,
    record: PropertyRecord | None,
    today: date | None = None,
    aerial_on: date | None = None,
) -> list[AdNote]:
    """The notes for this ad against this record: mismatches first, at most one confirmation,
    at most `MAX_NOTES` in all. Empty when there is nothing clear to say.

    `aerial_on` is the capture date of an aerial photo already held for this property (Vexcel).
    When the ad makes an exterior claim (pool, garage, yard) it is added last, if there is room,
    so the renter can look for themselves. It is a date, nothing is read from the picture, and it
    is never the confirming line."""
    if record is None or not claims.claims:
        return []
    today = today or date.today()
    found: list[AdNote] = []
    for rule in RULES:
        found.extend(rule(claims, record, today))
    mismatches = [n for n in found if not n.matches][:MAX_NOTES]
    confirm = next((n for n in found if n.matches), None)
    if confirm is not None and len(mismatches) < MAX_NOTES:
        mismatches.append(confirm)
    exterior = next((c for c in EXTERIOR if c in claims.kinds()), None)
    if (
        aerial_on is not None
        and exterior is not None
        and mismatches
        and len(mismatches) < MAX_NOTES
    ):
        mismatches.append(_note("aerial_date", exterior, ad_value=aerial_on.isoformat()))
    return mismatches

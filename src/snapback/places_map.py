"""The places map feed: one GeoJSON Feature per place CoStar has researched.

Built from the same supply and the same matching as `/search` (`search._supply`, `_all_matches`),
so a price on a pin and a price in the walk cannot differ. A feature holds only the keys in
`PROP_KEYS`: our id, the kind, whether a 3D scan is on record, counts, the lowest asking price,
units reported available, whether the place fits the brief, and the source. No address, no
office, no name, no phone, ever: the sheet (`GET /places/{pid}`) is where a company name is shown.

A place without coordinates in the record is counted in `n_unlocated`, never placed by guess.
The place list (the static part) is built once per index; the brief only sets `fits_brief`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from snapback.contracts import AS_OF, DataSource, PlaceMatch, RenterBrief
from snapback.search import _all_matches, _match, _source_of, _supply, plan_key

source_of = _source_of  # the data source of a lookups object (LIVE or FIXTURE)

PROP_KEYS = (
    "pid",
    "kind",
    "has_scan",
    "n_plans",
    "rent_from",
    "units_reported",
    "fits_brief",
    "source",
    "as_of",
)


class PlaceProps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pid: str
    kind: Literal["apartment", "house"]
    has_scan: bool
    n_plans: int
    rent_from: int | None  # the lowest asking price a month, whole dollars
    units_reported: int | None  # reported available as of CoStar's last research; None: not said
    fits_brief: bool
    source: DataSource
    as_of: str = AS_OF


class PlacePoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [lon, lat]


class PlaceFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: PlacePoint
    properties: PlaceProps


class PlacesMap(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    source: DataSource
    as_of: str = AS_OF
    n_places: int  # features drawn
    n_fit: int  # of those, how many fit the brief
    n_unlocated: int  # researched places the record gives no coordinates for (not drawn)
    features: list[PlaceFeature]


@dataclass(frozen=True)
class _Place:
    pid: str
    kind: str
    has_scan: bool
    n_plans: int
    rent_from: int | None
    units_reported: int | None
    lon: float
    lat: float


def _coordinates(lookups: Any) -> dict[str, tuple[float, float]]:
    """(lon, lat) by place id: apartment records, then house rentals."""
    out: dict[str, tuple[float, float]] = {}
    for pid, record in lookups.records().items():
        if record.lat is not None and record.lon is not None:
            out[pid] = (record.lon, record.lat)
    rentals = getattr(lookups, "rentals", None)
    for house in rentals() if callable(rentals) else []:
        lat, lon = getattr(house, "lat", None), getattr(house, "lon", None)
        if lat is not None and lon is not None:
            out[house.property_id] = (lon, lat)
    return out


def _build(lookups: Any) -> tuple[list[_Place], int]:
    coords = _coordinates(lookups)
    grouped: dict[str, list[Any]] = {}
    for raw in _supply(lookups):
        grouped.setdefault(raw.property_id, []).append(raw)
    places: list[_Place] = []
    unlocated = 0
    for pid in sorted(grouped):
        raws = grouped[pid]
        if pid not in coords:
            unlocated += 1
            continue
        prices = [p for r in raws for p in (r.rent_min, r.rent_max) if p is not None]
        units = [r.units_available for r in raws if r.units_available is not None]
        kind = raws[0].kind
        lon, lat = coords[pid]
        places.append(
            _Place(
                pid=pid,
                kind=kind,
                has_scan=any(r.has_scan for r in raws),
                n_plans=len({plan_key(r) for r in raws}),
                rent_from=min(prices) if prices else None,
                units_reported=sum(units) if units and kind == "apartment" else None,
                lon=lon,
                lat=lat,
            )
        )
    return places, unlocated


class PlacesIndex:
    """The places of one lookups object, built once and kept."""

    def __init__(self, lookups: Any) -> None:
        self._lookups = lookups
        self._lock = threading.Lock()
        self._built: tuple[list[_Place], int] | None = None

    def places(self) -> list[_Place]:
        with self._lock:
            if self._built is None:
                self._built = _build(self._lookups)
            return self._built[0]

    def unlocated(self) -> int:
        self.places()
        assert self._built is not None
        return self._built[1]

    def feed(self, brief: RenterBrief | None) -> PlacesMap:
        places = self.places()
        source = _source_of(self._lookups)
        # Every match, not the first `max_results`: the map flags all of them.
        fits = {m.property_id for m in _all_matches(brief or RenterBrief(), self._lookups)[1]}
        features = [
            PlaceFeature(
                id=p.pid,
                geometry=PlacePoint(coordinates=(p.lon, p.lat)),
                properties=PlaceProps(
                    pid=p.pid,
                    kind=p.kind,  # type: ignore[arg-type]
                    has_scan=p.has_scan,
                    n_plans=p.n_plans,
                    rent_from=p.rent_from,
                    units_reported=p.units_reported,
                    fits_brief=p.pid in fits,
                    source=source,
                ),
            )
            for p in places
        ]
        return PlacesMap(
            source=source,
            n_places=len(features),
            n_fit=sum(f.properties.fits_brief for f in features),
            n_unlocated=self.unlocated(),
            features=features,
        )


def build_places_map(brief: RenterBrief | None, lookups: Any) -> PlacesMap:
    """One-shot feed (tests and scripts); the API keeps a `PlacesIndex` per process."""
    return PlacesIndex(lookups).feed(brief)


# --- the place sheet ------------------------------------------------------------------------------

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class SheetAerial(BaseModel):
    source: DataSource
    captured_on: date | None = None
    line: str | None = None  # "Aerial photo captured Mar 14, 2025 (Vexcel)"; None without a date
    image_path: str | None = None  # our own route; the Vexcel key never leaves the server


class PlaceSheet(BaseModel):
    """What the map's sheet shows for one place: every priced plan with the same lines search
    builds, the company on record, the scan badge and the aerial. No address."""

    property_id: str
    kind: Literal["apartment", "house"]
    source: DataSource
    as_of: str = AS_OF
    office_on_record: str | None = None  # company name only
    has_3d_scan: bool = False
    scan_text: str | None = None
    walk_path: str | None = None  # Walk it first, when a scan is on record
    plans: list[PlaceMatch]
    aerial: SheetAerial | None = None


def captured_line(captured_on: date | None, source: DataSource) -> str | None:
    if captured_on is None:
        return None
    who = "Vexcel" if source is DataSource.LIVE else "fixture tile"
    day = f"{MONTHS[captured_on.month - 1]} {captured_on.day}, {captured_on.year}"
    return f"Aerial photo captured {day} ({who})"


def _walk_path(property_id: str, plans: list[PlaceMatch]) -> str | None:
    """The Walk it first link. A building with several floor plans needs the plan picked by its
    key (the tour answers 422 without it), the same way PlacesStrip.tourHref builds it."""
    if not any(p.has_3d_scan for p in plans):
        return None
    key = plans[0].plan_key
    q = f"?plan_key={quote(key, safe='')}" if key else ""
    return f"/tour/{quote(property_id, safe='')}{q}"


def place_sheet(property_id: str, lookups: Any) -> PlaceSheet | None:
    """The sheet for one place by id, whatever the budget; None when it has no priced plan."""
    source = _source_of(lookups)
    open_brief = RenterBrief(max_results=50)
    seen: set[str] = set()
    plans: list[PlaceMatch] = []
    for raw in _supply(lookups):
        if raw.property_id != property_id:
            continue
        match = _match(raw, open_brief, source)
        if match is None or (match.plan_key or "") in seen:
            continue
        seen.add(match.plan_key or "")
        plans.append(match)
    if not plans:
        return None
    from snapback.search import order_key

    plans.sort(key=order_key)
    first = plans[0]
    return PlaceSheet(
        property_id=property_id,
        kind=first.kind,
        source=source,
        office_on_record=first.office_on_record,
        has_3d_scan=any(p.has_3d_scan for p in plans),
        scan_text=first.scan_text if any(p.has_3d_scan for p in plans) else None,
        walk_path=_walk_path(property_id, plans),
        plans=plans,
    )


def fixture_tile_jpeg(property_id: str) -> bytes:
    """A plain team-made stand-in tile, labelled as one. Never Vexcel imagery."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    h = 0
    for ch in property_id:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    tall = 100 + (h % 7) * 12
    left = 180 + (h % 5) * 20
    img = Image.new("RGB", (640, 400), "#cfe0ea")
    draw = ImageDraw.Draw(img)
    draw.polygon([(0, 300), (640, 250), (640, 400), (0, 400)], fill="#b4d3e6")
    draw.rectangle([left, 280 - tall, left + 180, 280], fill="#ffffff")
    draw.text((250, 370), "Aerial tile (fixture)", fill="#43555f")
    out = BytesIO()
    img.save(out, format="JPEG", quality=80)
    return out.getvalue()

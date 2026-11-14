"""Vexcel aerial adapter (lane D, D2): oblique tiles per building, `AerialTile` out.

Fixture mode returns the synthetic tile in `fixtures/contracts/aerial_tile.json`. Live mode follows
the sponsor's Vexcel API 2.0 quickstart:

1. `GET oriented/collections` over a small square around the building (layer `urban`, product
   type `oblique`) lists which oblique directions exist and their last capture date. Obliques only
   exist in the `urban` layer; a 404 means no oblique coverage here.
2. `POST oriented/extract` with `product-type: oblique-<direction>` returns the image bytes.
   `direction="nadir"` uses `POST ortho/extract` over every ortho layer instead.

`X-API-KEY` comes from `.env`. A 429 is retried (Retry-After first, else exponential), and a wait
over 30 s gives up. One tile never takes more than 20 s in total (every request timeout and wait
counts against that budget), so a request path can call this safely. A malformed reply means no
tile, never an exception. `captured_on` is the oblique's last capture date; nadir (ortho) tiles
have none here, because the ortho extract does not report one, so theirs is always None.
Tiles are cached under `data/vexcel/` for at most 7 days (`make purge`
deletes them). Imagery never goes into git, a log, an issue or an outside model. No tile means
None, and the card ships record facts only.

`two_building_proof` puts the claimed building and the building the photos matched side by side,
with the distance between them.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from snapback.contracts import AerialTile, DataSource, PropertyRecord
from snapback.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_TILE = REPO_ROOT / "fixtures" / "contracts" / "aerial_tile.json"

BASE_URL = "https://api.vexcelgroup.com/v2"
ORTHO_LAYERS = "urban,urban-r,wide-area,urban-g"  # the API picks the best one here
OBLIQUE_LAYER = "urban"  # the only layer with obliques
HALF_SIDE_M = 40  # square around the building's point: 80 m across
BUFFER_M = 10
CACHE_DAYS = 7
MAX_RETRIES = 3
MAX_WAIT_S = 30.0  # a longer Retry-After is over budget: give up, ship record facts only
TIMEOUT_S = 60.0
TOTAL_BUDGET_S = 20.0  # one tile, end to end, across every request and wait
DIRECTIONS = ("north", "east", "south", "west", "nadir")
_FROM_SETTINGS = object()
_SAFE = re.compile(r"[^A-Za-z0-9_-]")

Sleep = Callable[[float], None]
_monotonic = time.monotonic  # replaced in tests
_BAD_REPLY = (ValueError, TypeError, AttributeError, KeyError)


class VexcelKeyMissingError(RuntimeError):
    pass


def _fixture(record: PropertyRecord, direction: str) -> AerialTile:
    tile = AerialTile.model_validate(json.loads(FIXTURE_TILE.read_text(encoding="utf-8")))
    return tile.model_copy(update={"property_id": record.property_id, "direction": direction})


def square_around(lat: float, lon: float, half_m: float = HALF_SIDE_M) -> str:
    """WKT square centred on the point. WKT is (lon lat), the reverse of lat, lon."""
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def distance_m(a: PropertyRecord, b: PropertyRecord) -> float | None:
    """Great-circle distance between two buildings, or None when either has no coordinates."""
    if None in (a.lat, a.lon, b.lat, b.lon):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))  # type: ignore[arg-type]
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _wait_s(response: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when the wait is over budget (or not a number)."""
    header = response.headers.get("Retry-After")
    if header is None:
        return float(2**attempt)
    try:
        wait = float(header)
    except ValueError:
        return float(2**attempt)
    if not math.isfinite(wait) or wait > MAX_WAIT_S:
        return None
    return max(0.0, wait)


def _send(
    http: httpx.Client,
    method: str,
    path: str,
    key: str,
    sleep: Sleep,
    deadline: float,
    **kwargs: Any,
) -> httpx.Response | None:
    """One API call with the 429 policy and the tile's time budget. None means rate limited past
    the budget or out of time."""
    for attempt in range(MAX_RETRIES + 1):
        remaining = deadline - _monotonic()
        if remaining <= 0:
            return None
        response = http.request(
            method,
            f"{BASE_URL}/{path}",
            headers={"X-API-KEY": key},
            timeout=min(TIMEOUT_S, remaining),
            **kwargs,
        )
        if response.status_code != 429:
            return response
        wait = _wait_s(response, attempt)
        if wait is None or attempt == MAX_RETRIES or _monotonic() + wait >= deadline:
            return None
        sleep(wait)
    return None


def _capture_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _oblique_capture(
    http: httpx.Client, wkt: str, key: str, direction: str, sleep: Sleep, deadline: float
) -> tuple[bool, date | None]:
    """(this direction exists here, its newest capture date). A malformed reply is (False, None)."""
    r = _send(
        http,
        "GET",
        "oriented/collections",
        key,
        sleep,
        deadline,
        params={
            "wkt": wkt,
            "srid": 4326,
            "layer": OBLIQUE_LAYER,
            "product-type": "oblique",
            "include": "product-type,collection,last-capture-date",
        },
    )
    if r is None or r.status_code != 200:
        return False, None  # 404: no oblique coverage at this location
    wanted = f"oblique-{direction}"
    try:
        dates = [
            _capture_date((f.get("properties") or {}).get("last-capture-date"))
            for f in r.json().get("features", [])
            if (f.get("properties") or {}).get("product-type") == wanted
        ]
    except _BAD_REPLY:
        return False, None
    found = [d for d in dates if d is not None]
    return bool(dates), max(found, default=None)


def get_tile(
    record: PropertyRecord,
    direction: str = "north",
    *,
    source: DataSource | None = None,
    data_dir: Path | None = None,
    api_key: str | None | object = _FROM_SETTINGS,
    client: httpx.Client | None = None,
    sleep: Sleep = time.sleep,
) -> AerialTile | None:
    settings = get_settings()
    source = source or settings.snapback_data_source
    if source == DataSource.FIXTURE:
        return _fixture(record, direction)
    if record.lat is None or record.lon is None or direction not in DIRECTIONS:
        return None
    if api_key is _FROM_SETTINGS:
        secret = settings.vexcel_api_key
        api_key = secret.get_secret_value() if secret else None
    if not api_key:
        raise VexcelKeyMissingError("VEXCEL_API_KEY is not set in .env; live tiles need it.")
    key = str(api_key)

    cache = Path(data_dir or settings.snapback_data_dir) / "vexcel"
    path = cache / f"{_SAFE.sub('_', record.property_id)}-{_SAFE.sub('_', direction)}.jpg"
    meta = path.with_suffix(".json")
    if path.is_file() and time.time() - path.stat().st_mtime < CACHE_DAYS * 24 * 3600:
        captured = None
        try:
            if meta.is_file():
                captured = _capture_date(json.loads(meta.read_text()).get("captured_on"))
        except (*_BAD_REPLY, OSError):
            captured = None  # a damaged meta file only loses the date, never the tile
        return AerialTile(
            property_id=record.property_id,
            source=DataSource.LIVE,
            direction=direction,
            captured_on=captured,
            path=str(path),
        )

    wkt = square_around(record.lat, record.lon)
    deadline = _monotonic() + TOTAL_BUDGET_S
    owns_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        captured: date | None = None
        if direction == "nadir":
            endpoint = "ortho/extract"
            body: dict[str, Any] = {"layer": ORTHO_LAYERS, "crop": "bounding_box"}
            body["image-format"] = "jpeg"
        else:
            exists, captured = _oblique_capture(http, wkt, key, direction, sleep, deadline)
            if not exists:
                return None
            endpoint = "oriented/extract"
            body = {
                "layer": OBLIQUE_LAYER,
                "product-type": f"oblique-{direction}",
                "rotation": "natural",
                "crop": "bbox",
                "image-format": "jpeg",
            }
        body |= {"wkt": wkt, "srid": 4326, "buffer-meter": BUFFER_M}
        r = _send(http, "POST", endpoint, key, sleep, deadline, json=body)
        if r is None or r.status_code != 200:
            return None
        if not r.headers.get("content-type", "").startswith("image/"):
            return None
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        meta.write_text(json.dumps({"captured_on": captured.isoformat() if captured else None}))
        return AerialTile(
            property_id=record.property_id,
            source=DataSource.LIVE,
            direction=direction,
            captured_on=captured,
            path=str(path),
        )
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            http.close()


@dataclass(frozen=True)
class TwoBuildingProof:
    """The claimed building and the building the photos matched, from the air, side by side."""

    claimed: AerialTile | None
    matched: AerialTile | None
    distance_m: float | None  # None when either record has no coordinates


def two_building_proof(
    claimed: PropertyRecord,
    matched: PropertyRecord,
    direction: str = "north",
    **kwargs: Any,
) -> TwoBuildingProof:
    return TwoBuildingProof(
        claimed=get_tile(claimed, direction, **kwargs),
        matched=get_tile(matched, direction, **kwargs),
        distance_m=distance_m(claimed, matched),
    )

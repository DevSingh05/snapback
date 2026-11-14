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
import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from snapback.contracts import (
    AerialProofResponse,
    AerialSideOut,
    AerialTile,
    DataSource,
    PropertyRecord,
)
from snapback.safety.paths import resolve_data_dir
from snapback.settings import get_settings

log = logging.getLogger(__name__)

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
TOTAL_BUDGET_S = 20.0  # one tile, end to end, across every request, wait and byte read
MAX_TILE_BYTES = 5 * 1024 * 1024  # a bigger reply is not a tile we want
MAX_COVERAGE_BYTES = 1024 * 1024  # the coverage JSON is a few KB
READ_SLICE_S = 2.0  # longest wait for any single read
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


@dataclass(frozen=True)
class _Reply:
    status: int
    content_type: str
    body: bytes


def _timeout(remaining: float) -> httpx.Timeout:
    """httpx applies a timeout to each connect and each read, not to the whole request, so every
    single read is also held to a short slice: one slow byte cannot overrun the tile budget."""
    return httpx.Timeout(min(TIMEOUT_S, remaining), read=min(READ_SLICE_S, remaining))


def _fetch(
    http: httpx.Client,
    method: str,
    path: str,
    key: str,
    sleep: Sleep,
    deadline: float,
    cap: int,
    **kwargs: Any,
) -> _Reply | None:
    """One API call, streamed, with the 429 policy, the tile deadline checked on every chunk and
    a size cap checked against Content-Length before any byte is read. Compressed replies are
    refused (decompression would get round the cap). None: rate limited past the budget, out of
    time, too big, or compressed. Used for both the coverage and the extract call."""
    headers = {"X-API-KEY": key, "Accept-Encoding": "identity"}
    for attempt in range(MAX_RETRIES + 1):
        remaining = deadline - _monotonic()
        if remaining <= 0:
            return None
        with http.stream(
            method,
            f"{BASE_URL}/{path}",
            headers=headers,
            timeout=_timeout(remaining),
            **kwargs,
        ) as response:
            if response.status_code == 429:
                wait = _wait_s(response, attempt)
                if wait is None or attempt == MAX_RETRIES or _monotonic() + wait >= deadline:
                    return None
                sleep(wait)
                continue
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                return None
            try:
                if int(response.headers.get("content-length", "")) > cap:
                    return None
            except ValueError:
                pass  # no Content-Length: the running count below still applies
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():  # identity only (checked above): no inflation
                size += len(chunk)
                if size > cap or _monotonic() > deadline:
                    return None
                chunks.append(chunk)
            return _Reply(
                response.status_code, response.headers.get("content-type", ""), b"".join(chunks)
            )
    return None


def _fetch_image(
    http: httpx.Client, path: str, key: str, sleep: Sleep, deadline: float, body: dict[str, Any]
) -> bytes | None:
    """POST an extract. The image bytes, or None (not a 200 image, empty, too big, too slow)."""
    reply = _fetch(http, "POST", path, key, sleep, deadline, MAX_TILE_BYTES, json=body)
    if reply is None or reply.status != 200 or not reply.content_type.startswith("image/"):
        return None
    return reply.body or None  # an empty 200 image is not a tile


def _capture_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _oblique_capture(
    http: httpx.Client, wkt: str, key: str, direction: str, sleep: Sleep, deadline: float
) -> tuple[bool, date | None]:
    """(this direction exists here, its newest capture date). A malformed reply is (False, None)."""
    r = _fetch(
        http,
        "GET",
        "oriented/collections",
        key,
        sleep,
        deadline,
        MAX_COVERAGE_BYTES,
        params={
            "wkt": wkt,
            "srid": 4326,
            "layer": OBLIQUE_LAYER,
            "product-type": "oblique",
            "include": "product-type,collection,last-capture-date",
        },
    )
    if r is None or r.status != 200:
        return False, None  # 404: no oblique coverage at this location
    wanted = f"oblique-{direction}"
    try:
        dates = [
            _capture_date((f.get("properties") or {}).get("last-capture-date"))
            for f in json.loads(r.body).get("features", [])
            if (f.get("properties") or {}).get("product-type") == wanted
        ]
    except _BAD_REPLY:
        return False, None
    found = [d for d in dates if d is not None]
    return bool(dates), max(found, default=None)


def known_capture(
    record: PropertyRecord,
    source: DataSource,
    direction: str = "north",
    *,
    data_dir: Path | None = None,
) -> date | None:
    """The capture date of an aerial tile we already hold for this property, or None.

    Reads the fixture tile, or the live cache beside a tile that is still fresh. It never calls
    Vexcel and needs no key, so a check can show the date without a network wait. Nothing is
    read from the picture. A missing, stale or damaged cache is None."""
    if source == DataSource.FIXTURE:
        return _fixture(record, direction).captured_on
    if direction not in DIRECTIONS:
        return None
    cache = resolve_data_dir(data_dir or get_settings().snapback_data_dir) / "vexcel"
    path = cache / f"{_SAFE.sub('_', record.property_id)}-{_SAFE.sub('_', direction)}.jpg"
    try:
        if not path.is_file() or time.time() - path.stat().st_mtime >= CACHE_DAYS * 24 * 3600:
            return None
        return _capture_date(json.loads(path.with_suffix(".json").read_text()).get("captured_on"))
    except (*_BAD_REPLY, OSError):
        return None


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

    cache = resolve_data_dir(data_dir or settings.snapback_data_dir) / "vexcel"
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
        content = _fetch_image(http, endpoint, key, sleep, deadline, body)
        if content is None:
            return None
        cache.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"captured_on": captured.isoformat() if captured else None}))
        # Atomic: write beside the tile, then rename, so the image route never reads half a jpg.
        tmp = path.with_suffix(".jpg.tmp")
        tmp.write_bytes(content)
        os.replace(tmp, path)
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


def known_capture_date(
    record: PropertyRecord,
    *,
    source: DataSource,
    data_dir: Path | None = None,
    direction: str = "north",
) -> date | None:
    """The aerial capture date for a building when it is already known, and never a fetch.

    Fixture: the synthetic tile's date. Live: the date saved beside a tile already cached in
    the last `CACHE_DAYS` days, else None. A damaged or missing meta file is "not known"."""
    if source == DataSource.FIXTURE:
        return _fixture(record, direction).captured_on
    root = resolve_data_dir(data_dir or get_settings().snapback_data_dir) / "vexcel"
    path = root / f"{_SAFE.sub('_', record.property_id)}-{_SAFE.sub('_', direction)}.jpg"
    meta = path.with_suffix(".json")
    try:
        fresh = path.is_file() and time.time() - path.stat().st_mtime < CACHE_DAYS * 24 * 3600
        if not fresh or not meta.is_file():
            return None
        return _capture_date(json.loads(meta.read_text()).get("captured_on"))
    except (*_BAD_REPLY, OSError):
        return None


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


# --- D9: the aerial proof a case shows (GET /cases/{id}/aerial) -------------------------------

PUBLIC_RECORD_FIELDS = {
    "property_id",
    "source",
    "market",
    "property_type",
    "floors",
    "year_built",
    "lat",
    "lon",
    "manager_company",
}


_kit_cache: dict[DataSource, dict[str, PropertyRecord]] = {}
_kit_lock = threading.Lock()


def kit_records(source: DataSource) -> dict[str, PropertyRecord]:
    """The kit's records, parsed once per process and source (a few thousand on the real kit),
    so a route does not re-read the JSONL on every request. A missing kit is not remembered: the
    next call looks again, so a kit unzipped after start-up is picked up."""
    from snapback.adapters import costar_jsonl

    with _kit_lock:
        if source in _kit_cache:
            return _kit_cache[source]
        try:
            records = costar_jsonl.load_records(source)
        except costar_jsonl.KitNotFoundError:
            return {}
        _kit_cache[source] = records
        return records


kit_records.cache_clear = _kit_cache.clear  # type: ignore[attr-defined]

# One pool for the whole process. `with ThreadPoolExecutor()` would wait for its threads on exit,
# so a timeout on the futures would bound nothing; this pool lets the route return on time.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aerial")


def _safe_tile(rec: PropertyRecord | None, direction: str, source: DataSource, **kw: Any):
    """get_tile, but a missing key or a disk error is no tile, never an error for the route."""
    if rec is None:
        return None
    try:
        return get_tile(rec, direction, source=source, **kw)
    except (VexcelKeyMissingError, OSError) as err:
        log.warning("aerial tile skipped: %s", type(err).__name__)
        return None


def _within(futures: list[Future], deadline: float) -> list[AerialTile | None]:
    out: list[AerialTile | None] = []
    for future in futures:
        try:
            out.append(future.result(timeout=max(0.0, deadline - _monotonic())))
        except FuturesTimeout:
            out.append(None)  # still running in the pool; this answer goes without it
    return out


def aerial_side(
    source: DataSource,
    property_id: str | None,
    *,
    direction: str = "north",
    records: dict[str, PropertyRecord] | None = None,
    **tile_kwargs: Any,
) -> AerialTile | None:
    """One building's tile, for the image route: only the side asked for, inside the budget."""
    if property_id is None:
        return None
    rec = (records if records is not None else kit_records(source)).get(property_id)
    deadline = _monotonic() + TOTAL_BUDGET_S
    future = _POOL.submit(_safe_tile, rec, direction, source, **tile_kwargs)
    return _within([future], deadline)[0]


def public_record(record: PropertyRecord) -> PropertyRecord:
    """The record trimmed to what the card shows: building facts and the company name. The phone
    hash, website host, units and rent bands never leave the server through this route."""
    return PropertyRecord.model_validate(record.model_dump(include=PUBLIC_RECORD_FIELDS))


def aerial_proof(
    case_id: str,
    source: DataSource,
    claimed_id: str | None,
    matched_id: str | None,
    *,
    direction: str = "north",
    records: dict[str, PropertyRecord] | None = None,
    image_url: Callable[[str], str] | None = None,
    **tile_kwargs: Any,
) -> AerialProofResponse:
    """Both buildings, fetched at the same time, each within the 20 s tile budget.

    `claimed_id` is the case's property id; `matched_id` the building a photo was located in when
    it was not the claimed one (None otherwise). `image_url(side)` builds our own image route for
    a live tile; fixture tiles get no URL (lane T draws its stand-in)."""
    if records is None:
        records = kit_records(source)
    claimed_rec = records.get(claimed_id) if claimed_id else None
    matched_rec = records.get(matched_id) if matched_id and matched_id != claimed_id else None

    deadline = _monotonic() + TOTAL_BUDGET_S  # one shared deadline for both tiles
    futures = [
        _POOL.submit(_safe_tile, rec, direction, source, **tile_kwargs)
        for rec in (claimed_rec, matched_rec)
    ]
    claimed_tile, matched_tile = _within(futures, deadline)

    def side(name: str, rec: PropertyRecord | None, t: AerialTile | None) -> AerialSideOut:
        url = (
            image_url(name) if image_url and t is not None and t.source == DataSource.LIVE else None
        )
        return AerialSideOut(tile=t, record=public_record(rec) if rec else None, image_url=url)

    matched = side("matched", matched_rec, matched_tile) if matched_rec else None
    return AerialProofResponse(
        case_id=case_id,
        source=source,
        claimed=side("claimed", claimed_rec, claimed_tile),
        matched=matched,
        distance_m=distance_m(claimed_rec, matched_rec) if claimed_rec and matched_rec else None,
    )

"""Vexcel aerial adapter (lane D, D2): one oblique tile per building, `AerialTile` out.

Fixture mode returns the synthetic tile in `fixtures/contracts/aerial_tile.json`. Live mode calls
the Vexcel REST API with `X-API-KEY` from `.env`, backs off on 429 (Retry-After first, then
exponential), and caches the tile under `data/vexcel/` for at most 7 days. Imagery never goes into
git, a log, an issue or an outside model.

If no tile comes back, this returns None and the card ships record facts only.

UNCONFIRMED: the tile route and its query names (`TILE_PATH`, `_params`) are our best reading of
the sponsor's description; check them with one live call once a key is in `.env`.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from snapback.contracts import AerialTile, DataSource, PropertyRecord
from snapback.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_TILE = REPO_ROOT / "fixtures" / "contracts" / "aerial_tile.json"

BASE_URL = "https://api.vexcelgroup.com/v2"
TILE_PATH = "/images/oblique"
CACHE_DAYS = 7
MAX_RETRIES = 3
MAX_WAIT_S = 30.0  # a longer Retry-After is over budget: give up, ship record facts only
TIMEOUT_S = 15.0
_FROM_SETTINGS = object()
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


class VexcelKeyMissingError(RuntimeError):
    pass


def _fixture(record: PropertyRecord) -> AerialTile:
    tile = AerialTile.model_validate(json.loads(FIXTURE_TILE.read_text(encoding="utf-8")))
    return tile.model_copy(update={"property_id": record.property_id})


def _params(record: PropertyRecord, direction: str) -> dict[str, str]:
    return {"lat": str(record.lat), "lon": str(record.lon), "orientation": direction}


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


def get_tile(
    record: PropertyRecord,
    direction: str = "north",
    *,
    source: DataSource | None = None,
    data_dir: Path | None = None,
    api_key: str | None | object = _FROM_SETTINGS,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AerialTile | None:
    settings = get_settings()
    source = source or settings.snapback_data_source
    if source == DataSource.FIXTURE:
        return _fixture(record)
    if record.lat is None or record.lon is None:
        return None
    if api_key is _FROM_SETTINGS:
        secret = settings.vexcel_api_key
        api_key = secret.get_secret_value() if secret else None
    if not api_key:
        raise VexcelKeyMissingError("VEXCEL_API_KEY is not set in .env; live tiles need it.")

    cache = Path(data_dir or settings.snapback_data_dir) / "vexcel"
    path = cache / f"{_SAFE.sub('_', record.property_id)}-{_SAFE.sub('_', direction)}.jpg"
    tile = AerialTile(
        property_id=record.property_id, source=DataSource.LIVE, direction=direction, path=str(path)
    )
    if path.is_file() and time.time() - path.stat().st_mtime < CACHE_DAYS * 24 * 3600:
        return tile

    owns_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        for attempt in range(MAX_RETRIES + 1):
            response = http.get(
                BASE_URL + TILE_PATH,
                params=_params(record, direction),
                headers={"X-API-KEY": str(api_key)},
            )
            if response.status_code == 429:
                wait = _wait_s(response, attempt)
                if wait is None:
                    return None
                if attempt < MAX_RETRIES:
                    sleep(wait)
                continue
            if response.status_code != 200:
                return None
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            return tile
        return None
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            http.close()

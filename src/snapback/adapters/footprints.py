"""Building footprints from OpenStreetMap (Overpass API), for the Vexcel footprint check.

Public data. Only the CLAIMED address's footprint is ever asked for (the anti-circularity rule
on #11): the scorer never sees where the ad's building really is. A footprint is the outline of
the OSM building that contains the claimed point; none means "not checked", never "wrong".

Answers are cached as JSON under the git-ignored data folder, so a measurement re-run makes no
new calls. Network errors and odd answers give None. Nothing here is ever committed.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
AROUND_M = 40  # buildings whose outline passes within this of the point
TIMEOUT_S = 10
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQUATOR = 111_320.0

LatLon = tuple[float, float]
Post = Callable[[str, str], dict[str, Any]]


def to_local_m(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """(east, north) metres of (lat, lon) from (lat0, lon0); fine over a few hundred metres."""
    east = (lon - lon0) * M_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))
    north = (lat - lat0) * M_PER_DEG_LAT
    return east, north


def contains(poly: list[tuple[float, float]], x: float, y: float) -> bool:
    """Is (x, y) inside the polygon (ray casting; the closing edge is implied)?"""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def polygons(doc: dict[str, Any]) -> list[list[LatLon]]:
    """Closed building outlines from an Overpass `out geom` answer (ways only)."""
    out: list[list[LatLon]] = []
    for el in doc.get("elements") or []:
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        pts = [(float(g["lat"]), float(g["lon"])) for g in geom if "lat" in g and "lon" in g]
        if len(pts) >= 4:
            out.append(pts)
    return out


def footprint_at(lat: float, lon: float, doc: dict[str, Any]) -> list[LatLon] | None:
    """The outline that contains (lat, lon), or None when no building does."""
    for poly in polygons(doc):
        local = [to_local_m(lat, lon, a, b) for a, b in poly]
        if contains(local, 0.0, 0.0):
            return poly
    return None


def _query(lat: float, lon: float) -> str:
    return (
        f'[out:json][timeout:{TIMEOUT_S}];way(around:{AROUND_M},{lat},{lon})["building"];out geom;'
    )


def _default_post(url: str, body: str) -> dict[str, Any]:
    import httpx  # lazily: only a LIVE measurement makes this call

    res = httpx.post(url, data={"data": body}, timeout=TIMEOUT_S + 5)
    res.raise_for_status()
    return res.json()


def fetch(
    lat: float | None,
    lon: float | None,
    *,
    cache_dir: Path | None = None,
    post: Post | None = None,
) -> list[LatLon] | None:
    """The claimed point's building outline from OSM, cached; None on no point, no building or
    any error."""
    if lat is None or lon is None:
        return None
    cache = cache_dir / f"{lat:.6f}_{lon:.6f}.json" if cache_dir else None
    doc: dict[str, Any] | None = None
    if cache and cache.is_file():
        try:
            doc = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
    if doc is None:
        try:
            doc = (post or _default_post)(OVERPASS_URL, _query(lat, lon))
        except Exception:  # network, HTTP or JSON: no evidence either way
            return None
        if not isinstance(doc, dict):
            return None
        if cache:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(doc), encoding="utf-8")
            except OSError:
                pass
    return footprint_at(lat, lon, doc)


def footprint_uv(
    lat0: float, lon0: float, poly: list[LatLon], ground_m: float
) -> list[tuple[float, float]]:
    """The outline in a north-up tile centred on (lat0, lon0) and `ground_m` metres across,
    as fractions of its width and height: (0.5, 0.5) is the centre, v grows southwards."""
    out = []
    for lat, lon in poly:
        east, north = to_local_m(lat0, lon0, lat, lon)
        out.append((0.5 + east / ground_m, 0.5 - north / ground_m))
    return out

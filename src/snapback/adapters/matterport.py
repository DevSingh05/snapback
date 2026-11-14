"""Matterport skybox fetch: six cube faces per sweep, cached under `data/` only.

Owner: lane V (the faces feed the locate index). Two backends behind `SNAPBACK_DATA_SOURCE`:

- `FixtureMatterport`: synthetic faces drawn from a seed for `fx-` model ids. No key needed.
- `LiveMatterport`: the Model API (GraphQL, HTTP Basic with MATTERPORT_API_KEY as the user and
  MATTERPORT_API_TOKEN as the password). Faces are written to `data/matterport/<model id>/`,
  which is git-ignored. Signed URLs are used once and never stored.

Sponsor terms: the faces are sponsor imagery. They never go into git or to an outside model,
and the cache is deleted after judging (`purge`).

Command line (prints counts only, never ids, URLs or pixels):

    uv run python -m snapback.adapters.matterport fetch            # the ids in DEMO_MODEL_IDS
    uv run python -m snapback.adapters.matterport fetch <model id> ...
"""

import argparse
import base64
import json
import shutil
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
from PIL import Image
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from snapback.contracts import DataSource

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_CACHE = REPO_ROOT / "data" / "matterport"
INDEX_CACHE = REPO_ROOT / "data" / "index"  # embeddings derived from the faces (terms 2.3)
FIXTURE_CACHE = REPO_ROOT / "data" / "fixture-matterport"
GRAPH_URL = "https://api.matterport.com/api/models/graph"
FACES = 6
FIXTURE_PREFIX = "fx-"

_QUERY_WITH_POSE = """
query($id: ID!) { model(id: $id) { locations {
  id position { x y z }
  panos { rotation { x y z w } skybox(resolution: "high") { children } }
} } }"""
# Each sweep's room and Matterport's classifications of it (issue #68: rooms carry no custom
# labels, but most are classified).
_QUERY_ROOMS = """
query($id: ID!) { model(id: $id) { locations {
  id room { classifications { label confidence } }
} } }"""
# The field set the kit probe has confirmed on our keys. Used if the pose fields are refused.
_QUERY_BARE = """
query($id: ID!) { model(id: $id) { locations {
  id panos { skybox(resolution: "high") { children } }
} } }"""


class MatterportSettings(BaseSettings):
    """The keys this adapter reads from the environment or `.env` (never printed)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    snapback_data_source: DataSource = DataSource.FIXTURE
    matterport_api_key: SecretStr | None = None
    matterport_api_token: SecretStr | None = None
    demo_model_ids: str | None = None  # comma-separated, local .env only (sponsor terms 3.2)

    def demo_ids(self) -> list[str]:
        return [part.strip() for part in (self.demo_model_ids or "").split(",") if part.strip()]


@dataclass(frozen=True)
class Sweep:
    model_id: str
    sweep_id: str
    faces: tuple[Path, ...]  # six local files, in the order the API lists them
    position: tuple[float, float, float] | None = None
    rotation_quat: tuple[float, float, float, float] | None = None  # x, y, z, w


class Matterport(Protocol):
    def sweeps(self, model_id: str) -> list[Sweep]: ...

    def room_labels(self, model_id: str) -> dict[str, str | None]:
        """Sweep id -> Matterport's most confident room classification ("Kitchen"), or None."""
        ...


def get_matterport(
    settings: MatterportSettings | None = None, *, cache_dir: Path | None = None
) -> Matterport:
    settings = settings or MatterportSettings()
    if settings.snapback_data_source is DataSource.FIXTURE:
        return FixtureMatterport(cache_dir or FIXTURE_CACHE)
    missing = [
        name
        for name, value in (
            ("MATTERPORT_API_KEY", settings.matterport_api_key),
            ("MATTERPORT_API_TOKEN", settings.matterport_api_token),
        )
        if value is None or not value.get_secret_value()
    ]
    if missing:
        raise RuntimeError(f"live Matterport needs {' and '.join(missing)} in .env")
    return LiveMatterport(
        settings.matterport_api_key.get_secret_value(),
        settings.matterport_api_token.get_secret_value(),
        cache_dir=cache_dir or LIVE_CACHE,
    )


# --- shared cache layout -----------------------------------------------------------------------


def _write_manifest(folder: Path, sweeps: list[Sweep]) -> None:
    rows = [
        {
            "sweep_id": sweep.sweep_id,
            "faces": [path.name for path in sweep.faces],
            "position": sweep.position,
            "rotation_quat": sweep.rotation_quat,
        }
        for sweep in sweeps
    ]
    (folder / "sweeps.json").write_text(json.dumps(rows, indent=1))


def _read_manifest(model_id: str, folder: Path) -> list[Sweep] | None:
    manifest = folder / "sweeps.json"
    if not manifest.is_file():
        return None
    sweeps = []
    for row in json.loads(manifest.read_text()):
        faces = tuple(folder / row["sweep_id"] / name for name in row["faces"])
        if not all(path.is_file() for path in faces):
            return None
        sweeps.append(
            Sweep(
                model_id=model_id,
                sweep_id=row["sweep_id"],
                faces=faces,
                position=tuple(row["position"]) if row["position"] else None,
                rotation_quat=tuple(row["rotation_quat"]) if row["rotation_quat"] else None,
            )
        )
    return sweeps


def _safe(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    if not cleaned:
        raise ValueError("empty id")
    return cleaned


# --- fixture backend ---------------------------------------------------------------------------


def synthetic_face(seed: int, size: int = 256) -> Image.Image:
    """A made-up cube face: smooth wall shading plus hard-edged blocks for doors and furniture."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] / size
    channels = []
    for _ in range(3):
        a, b, c = rng.uniform(-1, 1, 3)
        channels.append(120 + 60 * np.sin(3 * a * x + 2 * b * y + c))
    pixels = np.stack(channels, axis=-1)
    for _ in range(30):  # enough fixed structure for a crop to keep a few dozen corners
        x0, y0 = rng.integers(0, size - 24, 2)
        w, h = rng.integers(12, size // 4, 2)
        pixels[y0 : y0 + h, x0 : x0 + w] = rng.uniform(0, 255, 3)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")


class FixtureMatterport:
    """Synthetic sweeps for `fx-` model ids, drawn the same way every time."""

    SWEEPS = 4

    def __init__(self, cache_dir: Path = FIXTURE_CACHE) -> None:
        self.cache_dir = Path(cache_dir)

    def sweeps(self, model_id: str) -> list[Sweep]:
        if not model_id.startswith(FIXTURE_PREFIX):
            raise ValueError(f"fixture mode serves only {FIXTURE_PREFIX!r} model ids")
        folder = self.cache_dir / _safe(model_id)
        cached = _read_manifest(model_id, folder)
        if cached is not None:
            return cached

        base = sum(model_id.encode())
        sweeps = []
        for number in range(self.SWEEPS):
            sweep_id = f"fx-sweep-{number:02d}"
            (folder / sweep_id).mkdir(parents=True, exist_ok=True)
            faces = []
            for face in range(FACES):
                path = folder / sweep_id / f"face{face}.png"
                synthetic_face(base * 1000 + number * 10 + face).save(path)
                faces.append(path)
            sweeps.append(
                Sweep(
                    model_id=model_id,
                    sweep_id=sweep_id,
                    faces=tuple(faces),
                    position=(float(number), 1.4, 0.0),
                    rotation_quat=(0.0, 0.0, 0.0, 1.0),
                )
            )
        _write_manifest(folder, sweeps)
        return sweeps

    def room_labels(self, model_id: str) -> dict[str, str | None]:
        return {}


# --- live backend ------------------------------------------------------------------------------


MAX_RETRY_SLEEP_S = 30.0


def _retry_delay(header: str | None, attempt: int) -> float:
    """Seconds to wait before retrying a 429: the server's Retry-After in seconds when it is a
    number, else exponential backoff; never longer than MAX_RETRY_SLEEP_S (an HTTP-date or a
    value like 3600 must not stall a case)."""
    try:
        delay = float(header) if header is not None else float(2**attempt)
    except ValueError:
        delay = float(2**attempt)
    return min(max(delay, 0.0), MAX_RETRY_SLEEP_S)


class LiveMatterport:
    RETRIES = 4

    def __init__(
        self,
        key: str,
        token: str,
        *,
        cache_dir: Path = LIVE_CACHE,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self._auth = "Basic " + base64.b64encode(f"{key}:{token}".encode()).decode()
        self._client = client or httpx.Client(timeout=30.0)

    def sweeps(self, model_id: str) -> list[Sweep]:
        folder = self.cache_dir / _safe(model_id)
        cached = _read_manifest(model_id, folder)
        if cached is not None:
            return cached

        locations, with_pose = self._locations(model_id)
        sweeps = []
        for location in locations:
            sweep_id = _safe(str(location.get("id") or f"sweep{len(sweeps)}"))
            panos = location.get("panos") or []
            panos = [panos] if isinstance(panos, dict) else panos
            pano = next((p for p in panos if ((p or {}).get("skybox") or {}).get("children")), None)
            if pano is None:
                continue
            urls = pano["skybox"]["children"][:FACES]
            (folder / sweep_id).mkdir(parents=True, exist_ok=True)
            faces = []
            for number, url in enumerate(urls):
                path = folder / sweep_id / f"face{number}.jpg"
                if not path.is_file():
                    path.write_bytes(self._get(url).content)
                faces.append(path)
            position = rotation = None
            if with_pose:
                p, r = location.get("position"), pano.get("rotation")
                position = (p["x"], p["y"], p["z"]) if p else None
                rotation = (r["x"], r["y"], r["z"], r["w"]) if r else None
            sweeps.append(Sweep(model_id, sweep_id, tuple(faces), position, rotation))
        if not sweeps:
            # Never cache an empty model: a later call should ask the API again.
            raise RuntimeError(
                f"model has no skybox sweeps ({len(locations)} locations, none with faces)"
            )
        _write_manifest(folder, sweeps)
        return sweeps

    def room_labels(self, model_id: str) -> dict[str, str | None]:
        cache = self.cache_dir / _safe(model_id) / "rooms.json"
        if cache.is_file():
            return json.loads(cache.read_text())
        payload = self._post({"query": _QUERY_ROOMS, "variables": {"id": model_id}}).json()
        if payload.get("errors"):
            return {}
        labels: dict[str, str | None] = {}
        for location in ((payload.get("data") or {}).get("model") or {}).get("locations") or []:
            kinds = ((location.get("room") or {}).get("classifications")) or []
            best = max(kinds, key=lambda k: k.get("confidence") or 0, default=None)
            labels[_safe(str(location.get("id")))] = (best or {}).get("label")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(labels))
        return labels

    def _locations(self, model_id: str) -> tuple[list[dict], bool]:
        for query, with_pose in ((_QUERY_WITH_POSE, True), (_QUERY_BARE, False)):
            payload = self._post({"query": query, "variables": {"id": model_id}}).json()
            if not payload.get("errors"):
                model = (payload.get("data") or {}).get("model") or {}
                return list(model.get("locations") or []), with_pose
        codes = sorted(
            {str((e.get("extensions") or {}).get("code", "error")) for e in payload["errors"]}
        )
        raise RuntimeError(f"Matterport GraphQL refused the model: {', '.join(codes)}")

    def _post(self, body: dict) -> httpx.Response:
        return self._send("POST", GRAPH_URL, json=body, headers={"Authorization": self._auth})

    def _get(self, url: str) -> httpx.Response:
        return self._send("GET", url)

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(self.RETRIES + 1):
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as error:
                # A dropped or refused connection: back off and try again, like a 429.
                if attempt == self.RETRIES:
                    # The error type only: its message may echo a signed URL.
                    raise RuntimeError(
                        f"Matterport request failed: network ({type(error).__name__})"
                    ) from None
                time.sleep(2**attempt)
                continue
            if response.status_code != 429 or attempt == self.RETRIES:
                break
            time.sleep(_retry_delay(response.headers.get("retry-after"), attempt))
        if response.status_code >= 400:
            # Status only: the URL may carry a signature, and the body may echo the request.
            raise RuntimeError(f"Matterport request failed: HTTP {response.status_code}")
        return response


def purge(cache_dir: Path = LIVE_CACHE, *, index_dir: Path = INDEX_CACHE) -> None:
    """Delete every cached face and every index built from them (sponsor terms: all copies
    and derivatives deleted after the event)."""
    shutil.rmtree(cache_dir, ignore_errors=True)
    shutil.rmtree(index_dir, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.adapters.matterport")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="fetch skybox faces into data/ (counts printed only)")
    fetch.add_argument("model_ids", nargs="*", help="defaults to DEMO_MODEL_IDS from .env")
    sub.add_parser("purge", help="delete the live face cache and the locate index")
    args = parser.parse_args(argv)

    if args.command == "purge":
        purge()
        print("purged the live Matterport cache and the locate index")
        return 0

    settings = MatterportSettings()
    ids = args.model_ids or settings.demo_ids()
    if not ids:
        print("no model ids: pass some, or set DEMO_MODEL_IDS in .env")
        return 2
    adapter = get_matterport(settings)
    for number, model_id in enumerate(ids, start=1):
        started = time.monotonic()
        sweeps = adapter.sweeps(model_id)
        faces = sum(len(sweep.faces) for sweep in sweeps)
        posed = sum(sweep.position is not None for sweep in sweeps)
        print(
            f"building {number}: sweeps {len(sweeps)}, faces {faces}, with pose {posed}, "
            f"{time.monotonic() - started:.1f} s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

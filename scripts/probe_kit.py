#!/usr/bin/env python3
"""Probe the CoStar hackathon kit and print field names and counts only.

Never prints record values, addresses, names, ids or URLs, so the output is
safe to paste into a GitHub issue.

Usage:
    python3 scripts/probe_kit.py
    python3 scripts/probe_kit.py --kit path/to/costar-hackathon-kit
    python3 scripts/probe_kit.py --all-keys        # every key path with counts
    python3 scripts/probe_kit.py --no-matterport   # skip the network check

Matterport check: if MATTERPORT_API_KEY and MATTERPORT_API_TOKEN are set
(in .env or the environment), it loads 3 Houston multifamily models through the
Model API and prints only ok/fail and sweep counts.
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KIT = REPO_ROOT / "data" / "raw" / "costar" / "costar-hackathon-kit"
HOUSTON_MARKET_ID = 14  # primaryAddress.researchMarketId (reported by another team; probe confirms)
MULTIFAMILY_TYPE = 11  # propertyType
MATTERPORT_REF_TYPES = {36, 234}  # attachments[].videoExternalReferenceType
MATTERPORT_GRAPH_URL = "https://api.matterport.com/api/models/graph"


def _ssl_context():
    """Use certifi's CA bundle when present (python.org Python on macOS ships without one)."""
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


INTEREST = re.compile(
    r"rent|owner|contact|manag|leas|phone|email|photo|image|url|price|floor ?plan|unit", re.I
)


def load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def find_jsonl(kit: Path) -> Path | None:
    if kit.is_file() and kit.suffix == ".jsonl":
        return kit
    if not kit.is_dir():
        return None
    preferred = sorted(kit.rglob("commercial-property.jsonl"))
    if preferred:
        return preferred[0]
    others = sorted(kit.rglob("*.jsonl"), key=lambda p: p.stat().st_size, reverse=True)
    return others[0] if others else None


def walk(obj, path: str, keys: collections.Counter) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            q = f"{path}.{k}" if path else k
            keys[q] += 1
            walk(v, q, keys)
    elif isinstance(obj, list):
        for v in obj[:50]:
            walk(v, path + "[]", keys)


def matterport_ids(record: dict) -> list[str]:
    """Model ids from attachments[] anywhere in the record (never printed)."""
    found: list[str] = []

    def visit(o):
        if isinstance(o, dict):
            if o.get("videoExternalReferenceType") in MATTERPORT_REF_TYPES and o.get("videoKey"):
                found.append(str(o["videoKey"]))
            for v in o.values():
                visit(v)
        elif isinstance(o, list):
            for v in o:
                visit(v)

    visit(record)
    return list(dict.fromkeys(found))


def probe_model(
    model_id: str, token_id: str, secret: str, timeout: float = 20.0
) -> tuple[bool, str, int, int]:
    """Returns (ok, reason, sweeps, sweeps_with_skybox). Never returns URLs or names."""
    query = (
        "query($id: ID!) { model(id: $id) { locations { id "
        'panos { skybox(resolution: "high") { children } } } } }'
    )
    body = json.dumps({"query": query, "variables": {"id": model_id}}).encode()
    auth = base64.b64encode(f"{token_id}:{secret}".encode()).decode()
    req = urllib.request.Request(
        MATTERPORT_GRAPH_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", 0, 0
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, f"network: {type(e).__name__}", 0, 0
    if payload.get("errors"):
        codes = sorted(
            {str((err.get("extensions") or {}).get("code", "error")) for err in payload["errors"]}
        )
        return False, "graphql: " + ",".join(codes), 0, 0
    model = (payload.get("data") or {}).get("model") or {}
    locations = model.get("locations") or []
    with_sky = 0
    for loc in locations:
        panos = loc.get("panos") or []
        if isinstance(panos, dict):
            panos = [panos]
        if any(((p or {}).get("skybox") or {}).get("children") for p in panos):
            with_sky += 1
    return True, "ok", len(locations), with_sky


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--kit", type=Path, default=DEFAULT_KIT, help="kit folder or the .jsonl file")
    ap.add_argument("--env", type=Path, default=REPO_ROOT / ".env", help=".env file with keys")
    ap.add_argument("--all-keys", action="store_true", help="print every key path with its count")
    ap.add_argument(
        "--no-matterport", action="store_true", help="skip the Matterport Model API check"
    )
    ap.add_argument(
        "--models", type=int, default=3, help="how many Houston multifamily models to try"
    )
    args = ap.parse_args()

    load_dotenv(args.env)
    kit = args.kit.expanduser().resolve()
    print("== SNAPBACK kit probe (field names and counts only; safe to paste) ==")

    if kit.is_dir():
        top = sorted(p.name for p in kit.iterdir())
        docs = [n for n in top if re.search(r"readme|license|terms|notice", n, re.I)]
        print(
            f"kit folder: found, {len(top)} top-level entries; "
            f"docs to read first: {docs or 'none found'}"
        )

    jsonl = find_jsonl(kit)
    if jsonl is None:
        print(f"ERROR: no .jsonl found under {kit}")
        print("Unzip the kit to data/raw/costar/costar-hackathon-kit/ or pass --kit <folder>.")
        return 2
    print(f"jsonl: {jsonl.name}")

    keys: collections.Counter = collections.Counter()
    markets: collections.Counter = collections.Counter()
    types: collections.Counter = collections.Counter()
    records = bad = with_mp = 0
    houston_mf = houston_mf_mp = 0
    candidates: list[tuple[int, str]] = []  # (number of models, first model id); ids never printed

    with jsonl.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            records += 1
            walk(rec, "", keys)
            market = (rec.get("primaryAddress") or {}).get("researchMarketId")
            ptype = rec.get("propertyType")
            markets[market] += 1
            types[ptype] += 1
            ids = matterport_ids(rec)
            if ids:
                with_mp += 1
            if market == HOUSTON_MARKET_ID and ptype == MULTIFAMILY_TYPE:
                houston_mf += 1
                if ids:
                    houston_mf_mp += 1
                    candidates.append((len(ids), ids[0]))

    print(f"records: {records}  (unparseable lines: {bad})")
    print(f"records with a Matterport model id: {with_mp}")
    print("research markets (id: count):", ", ".join(f"{k}: {v}" for k, v in markets.most_common()))
    print("property types (code: count):", ", ".join(f"{k}: {v}" for k, v in types.most_common()))
    print(
        f"Houston (market {HOUSTON_MARKET_ID}) multifamily: {houston_mf}; "
        f"with a Matterport model id: {houston_mf_mp}"
    )
    print(f"distinct key paths: {len(keys)}")
    print("-- keys that may hold rent, owner, contact, photos or urls (count: path) --")
    hits = [(n, k) for k, n in keys.items() if INTEREST.search(k.split(".")[-1])]
    for n, k in sorted(hits, key=lambda t: t[1]) or [(0, "none")]:
        print(f"{n}: {k}")
    if args.all_keys:
        print("-- all key paths (count: path) --")
        for k in sorted(keys):
            print(f"{keys[k]}: {k}")

    print("-- Matterport Model API --")
    token_id = os.environ.get("MATTERPORT_API_KEY", "")
    secret = os.environ.get("MATTERPORT_API_TOKEN", "")
    if args.no_matterport:
        print("skipped (--no-matterport)")
    elif not (token_id and secret):
        print("skipped: MATTERPORT_API_KEY / MATTERPORT_API_TOKEN not set in .env")
    elif not candidates:
        print("skipped: no Houston multifamily record with a Matterport model id")
    else:
        candidates.sort(key=lambda t: (-t[0], t[1]))
        loaded = 0
        for i, (_, model_id) in enumerate(candidates[: args.models], start=1):
            ok, reason, sweeps, sky = probe_model(model_id, token_id, secret)
            loaded += ok
            print(
                f"building {i}: {'OK' if ok else 'FAIL'} ({reason}); "
                f"sweeps {sweeps}; sweeps with skybox faces {sky}"
            )
        print(f"models loaded: {loaded} of {min(args.models, len(candidates))}")
        print(
            "DATA GATE: GO"
            if loaded >= 3
            else "DATA GATE: not yet (need 3 Houston or LA multifamily models loading)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

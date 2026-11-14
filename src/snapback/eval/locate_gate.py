"""Locate gate (V2 #28): how many held-out views of a twin are placed, with pose, and how many
views of another building are placed elsewhere.

Nobody on the team can photograph these buildings, so the held-out views are RENDERS of the
live scans at viewpoints the index never stored: random yaw (never within 5 degrees of a face
centre), pitch -15 to 10, field of view 55 to 75, JPEG at quality 70, brightness 85 to 115%.
Every line this prints says so. Counts only: no ids, no pixels.

    uv run python -m snapback.eval.locate_gate --index data/index/all-tiny --n 20
"""

import argparse
import io
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

from snapback.adapters.matterport import MatterportSettings, get_matterport
from snapback.contracts import DataSource, LocateStatus
from snapback.vision.locate.cube import angle_between, look_rotation, render
from snapback.vision.locate.geometry import matrix_from_quaternion
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.locate import Catalog, Locator, ModelInfo

REPO_ROOT = Path(__file__).resolve().parents[3]


def held_out_view(sweep, rng: random.Random) -> tuple[Image.Image, np.ndarray, float]:
    faces = [Image.open(path).convert("RGB") for path in sweep.faces]
    while True:
        yaw = rng.uniform(0, 360)
        if min(abs(yaw - c) for c in (0, 90, 180, 270, 360)) > 5:
            break
    pitch, hfov = rng.uniform(-15, 10), rng.uniform(55, 75)
    rotation = look_rotation(yaw, pitch)
    view = render(faces, rotation, hfov, (1024, 768))
    view = ImageEnhance.Brightness(view).enhance(rng.uniform(0.85, 1.15))
    buffer = io.BytesIO()
    view.save(buffer, format="JPEG", quality=70)
    buffer.seek(0)
    pano = matrix_from_quaternion(sweep.rotation_quat) if sweep.rotation_quat else np.eye(3)
    return Image.open(buffer).convert("RGB"), pano @ rotation[:, 2], hfov


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.eval.locate_gate")
    parser.add_argument("--index", type=Path, default=REPO_ROOT / "data" / "index" / "demo")
    parser.add_argument("--cache", type=Path, help="face cache (default by data source)")
    parser.add_argument("--claimed", type=int, default=1, help="which DEMO_MODEL_IDS entry")
    parser.add_argument("--n", type=int, default=20, help="held-out views of the claimed twin")
    parser.add_argument("--n-other", type=int, default=5, help="views of another building")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--matcher", choices=("disk", "patch"), default="disk")
    parser.add_argument("--source", choices=[s.value for s in DataSource])
    args = parser.parse_args(argv)

    settings = MatterportSettings()
    if args.source:
        settings = settings.model_copy(update={"snapback_data_source": DataSource(args.source)})
    adapter = get_matterport(settings, cache_dir=args.cache)
    index = LocateIndex.load(args.index)
    if index.embedder is None:
        from snapback.vision.embed import Dinov2Embedder

        index = LocateIndex.load(args.index, Dinov2Embedder())
    model_ids = sorted(index.model_ids())
    demo = settings.demo_ids()
    claimed = demo[args.claimed - 1] if demo else model_ids[0]
    if claimed not in model_ids:
        print("the claimed demo twin is not in this index")
        return 2
    sweeps = {m: adapter.sweeps(m) for m in model_ids}
    # Gate catalog: one property per twin (the kit's grouping is lane D's; this gate only asks
    # "this twin or another one").
    catalog = Catalog(
        ModelInfo(m, f"gate-prop-{m}", None, adapter.room_labels(m)) for m in model_ids
    )
    if args.matcher == "disk":
        from snapback.vision.locate.verify import DiskLightGlue

        matcher = DiskLightGlue()
    else:
        from snapback.vision.locate.verify import PatchMatcher

        matcher = PatchMatcher()
    locator = Locator(index, sweeps, catalog, matcher)
    rng = random.Random(args.seed)

    located = right_sweep = pose_ok = 0
    errors, seconds = [], []
    for number in range(args.n):
        sweep = rng.choice(sweeps[claimed])
        photo, truth, _ = held_out_view(sweep, rng)
        started = time.monotonic()
        result = locator.locate(f"gate-{number}", {"p": photo}, f"gate-prop-{claimed}")
        seconds.append(time.monotonic() - started)
        placed = result.photos[0]
        if placed.status is LocateStatus.LOCATED_IN_CLAIMED:
            located += 1
            right_sweep += placed.pano_id == sweep.sweep_id
            pose = result.poses.get("p")
            if pose is not None and placed.pano_id == sweep.sweep_id:
                looks = matrix_from_quaternion(pose.rotation_quat) @ np.array([0.0, 0.0, -1.0])
                error = angle_between(looks, truth)
                errors.append(error)
                pose_ok += error < 15

    others = [m for m in model_ids if m != claimed]
    elsewhere = 0
    for number in range(args.n_other if others else 0):
        model = rng.choice(others)
        photo, _, _ = held_out_view(rng.choice(sweeps[model]), rng)
        result = locator.locate(f"gate-o{number}", {"p": photo}, f"gate-prop-{claimed}")
        elsewhere += result.photos[0].status is LocateStatus.LOCATED_ELSEWHERE

    label = "RENDERS of live scans at unseen viewpoints, not phone photos"
    print(
        f"locate gate ({label}); index: {len(model_ids)} twins, {len(index)} views, "
        f"embedder {index.embedder_name}; matcher {matcher.name}; "
        f"thresholds {locator.thresholds.version}"
    )
    print(f"placed in the claimed twin: {located} of {args.n}")
    print(f"  at the sweep it was rendered from: {right_sweep} of {args.n}")
    print(
        f"  pose within 15 degrees: {pose_ok} of {args.n}"
        + (f" (median error {np.median(errors):.1f} deg)" if errors else "")
    )
    print(
        f"views of another building placed elsewhere: {elsewhere} of "
        f"{args.n_other if others else 0}"
    )
    print(f"seconds per photo: median {np.median(seconds):.1f}, max {max(seconds):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""A team walkthrough video as a twin (V3 #29), so the live demo can place a photo taken in a
room we are standing in (Moment 3), with the same index and LocateResult as the scans.

Frames are sampled every `every_s` seconds; each frame becomes a one-face "sweep" with id
`frame-NNNN`. A frame has no 3D position, so a photo placed in a video twin gets a frame id
(`pano_id`) but no pose. Frames and the index go under `data/` (git-ignored); the video is
team-made.

    uv run python -m snapback.vision.locate.video_index build walk.mp4 --name lounge
    uv run python -m snapback.vision.locate.video_index locate photo.jpg --name lounge
"""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageSequence, UnidentifiedImageError

from snapback.adapters.matterport import Sweep
from snapback.vision.embed import Embedder, TinyEmbedder
from snapback.vision.locate.index import INDEX_ROOT, LocateIndex

REPO_ROOT = Path(__file__).resolve().parents[4]
VIDEO_ROOT = REPO_ROOT / "data" / "video"
MAX_SIDE = 1280


def _shrink(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    scale = min(1.0, MAX_SIDE / max(image.size))
    if scale < 1.0:
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return image


def _frames_pil(path: Path, every_s: float, max_frames: int) -> list[tuple[float, Image.Image]]:
    out, clock, next_at = [], 0.0, 0.0
    with Image.open(path) as clip:
        for frame in ImageSequence.Iterator(clip):
            if clock + 1e-9 >= next_at:
                out.append((clock, _shrink(frame.copy())))
                next_at += every_s
                if len(out) >= max_frames:
                    break
            clock += (frame.info.get("duration") or 100) / 1000.0
    return out


def _frames_cv(path: Path, every_s: float, max_frames: int) -> list[tuple[float, Image.Image]]:
    import cv2  # in the vision extra

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    out, number, next_at = [], 0, 0.0
    try:
        while len(out) < max_frames:
            ok, bgr = capture.read()
            if not ok:
                break
            at = number / fps
            if at + 1e-9 >= next_at:
                out.append((at, _shrink(Image.fromarray(bgr[:, :, ::-1]))))
                next_at += every_s
            number += 1
    finally:
        capture.release()
    return out


def sample_frames(
    path: Path, every_s: float = 0.5, max_frames: int = 240
) -> list[tuple[float, Image.Image]]:
    """(seconds, frame) every `every_s` seconds, at most `max_frames`, frames at most 1280 px."""
    path = Path(path)
    frames: list[tuple[float, Image.Image]] = []
    try:
        frames = _frames_pil(path, every_s, max_frames)
    except (UnidentifiedImageError, OSError):
        frames = []
    if len(frames) <= 1:  # a still image, or a real video Pillow cannot read
        try:
            video = _frames_cv(path, every_s, max_frames)
        except ImportError:
            video = []
        frames = video or frames
    if not frames:
        raise ValueError(f"could not read any frames from {path.name}")
    return frames


def build_video_twin(
    video: Path,
    model_id: str,
    out_dir: Path,
    embedder: Embedder,
    every_s: float = 0.5,
    max_frames: int = 240,
) -> tuple[list[Sweep], LocateIndex]:
    folder = Path(out_dir) / model_id
    folder.mkdir(parents=True, exist_ok=True)
    sweeps, manifest = [], []
    for number, (at, frame) in enumerate(sample_frames(video, every_s, max_frames)):
        sweep_id = f"frame-{number:04d}"
        path = folder / f"{sweep_id}.jpg"
        frame.save(path, quality=92)
        sweeps.append(Sweep(model_id=model_id, sweep_id=sweep_id, faces=(path,)))
        manifest.append({"sweep_id": sweep_id, "seconds": round(at, 3), "file": path.name})
    (folder / "frames.json").write_text(json.dumps(manifest, indent=1))
    return sweeps, LocateIndex.build(model_id, sweeps, embedder)


def load_video_twin(model_id: str, out_dir: Path = VIDEO_ROOT) -> list[Sweep]:
    folder = Path(out_dir) / model_id
    rows = json.loads((folder / "frames.json").read_text())
    return [Sweep(model_id, row["sweep_id"], (folder / row["file"],)) for row in rows]


def _embedder(name: str) -> Embedder:
    if name == "tiny":
        return TinyEmbedder()
    from snapback.vision.embed import Dinov2Embedder

    return Dinov2Embedder()


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - needs a real video
    parser = argparse.ArgumentParser(prog="python -m snapback.vision.locate.video_index")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="sample a walkthrough video and index its frames")
    build.add_argument("video", type=Path)
    build.add_argument("--name", required=True)
    build.add_argument("--every", type=float, default=0.5, help="seconds between frames")
    build.add_argument("--embedder", choices=("dinov2", "tiny"), default="dinov2")
    find = sub.add_parser("locate", help="place one photo in a video twin and time it")
    find.add_argument("photo", type=Path)
    find.add_argument("--name", required=True)
    find.add_argument("--matcher", choices=("disk", "patch"), default="disk")
    args = parser.parse_args(argv)

    model_id = f"walk-{args.name}"
    if args.command == "build":
        started = time.monotonic()
        sweeps, index = build_video_twin(
            args.video, model_id, VIDEO_ROOT, _embedder(args.embedder), every_s=args.every
        )
        index.save(INDEX_ROOT / model_id)
        print(
            f"frames {len(sweeps)}, views {len(index)}, embedder {index.embedder_name}, "
            f"{time.monotonic() - started:.1f} s; saved to {model_id}/"
        )
        return 0

    from snapback.vision.locate.locate import Catalog, Locator, ModelInfo

    index = LocateIndex.load(INDEX_ROOT / model_id)
    if index.embedder is None:
        index = LocateIndex.load(INDEX_ROOT / model_id, _embedder("dinov2"))
    if args.matcher == "disk":
        from snapback.vision.locate.verify import DiskLightGlue

        matcher = DiskLightGlue()
    else:
        from snapback.vision.locate.verify import PatchMatcher

        matcher = PatchMatcher()
    locator = Locator(
        index,
        {model_id: load_video_twin(model_id)},
        Catalog([ModelInfo(model_id, f"room-{args.name}")]),
        matcher,
    )
    with Image.open(args.photo) as opened:
        photo = opened.convert("RGB")
    started = time.monotonic()
    result = locator.locate("live", {"live": photo}, f"room-{args.name}")
    placed = result.photos[0]
    print(
        f"{placed.status.value}, frame {placed.pano_id}, inliers {placed.inliers}, "
        f"{time.monotonic() - started:.1f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

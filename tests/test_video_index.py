"""V3: a team walkthrough video as a twin: sampled frames, the same index and LocateResult."""

import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from snapback.contracts import LocateStatus
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.locate import Catalog, Locator, ModelInfo
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import PatchMatcher
from snapback.vision.locate.video_index import build_video_twin, sample_frames

THRESHOLDS = replace(load_thresholds(), min_inliers=12, stop_at_inliers=60)


def room_panorama(seed: int = 3, size: tuple[int, int] = (1600, 360)) -> Image.Image:
    rng = np.random.default_rng(seed)
    width, height = size
    y, x = np.mgrid[0:height, 0:width] / width
    pixels = np.stack(
        [120 + 60 * np.sin(5 * a * x + 3 * b * y) for a, b in rng.uniform(-1, 1, (3, 2))], axis=-1
    )
    for _ in range(140):
        x0, y0 = rng.integers(0, width - 30), rng.integers(0, height - 30)
        w, h = rng.integers(10, 70), rng.integers(10, 70)
        pixels[y0 : y0 + h, x0 : x0 + w] = rng.uniform(0, 255, 3)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")


def walkthrough_clip(path, seconds: float = 6.0, fps: int = 10) -> Image.Image:
    """A synthetic phone pan across a room, saved as an animated GIF (no video codec needed)."""
    room = room_panorama()
    frames = []
    count = int(seconds * fps)
    for i in range(count):
        left = int((room.width - 480) * i / (count - 1))
        frames.append(room.crop((left, 0, left + 480, 360)))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)
    return room


def test_frames_sampled_and_indexed_from_fixture_clip(tmp_path):
    clip = tmp_path / "walk.gif"
    room = walkthrough_clip(clip)

    frames = sample_frames(clip, every_s=0.5)
    assert len(frames) == 12
    assert [round(t, 1) for t, _ in frames[:3]] == [0.0, 0.5, 1.0]

    sweeps, index = build_video_twin(clip, "walk-fx", tmp_path / "out", TinyEmbedder(), every_s=0.5)
    assert len(sweeps) == 12 and all(len(s.faces) == 1 for s in sweeps)
    assert all(s.position is None for s in sweeps)
    assert index.model_ids() == {"walk-fx"}

    catalog = Catalog([ModelInfo("walk-fx", "fx-demo-room")])
    locator = Locator(index, {"walk-fx": sweeps}, catalog, PatchMatcher(), THRESHOLDS)
    # A "live" photo: part of the room as the 3-second frame shows it.
    photo = room.crop((560 + 40, 30, 560 + 400, 330))
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    result = locator.locate("fx-live", {"live": Image.open(buffer).convert("RGB")}, "fx-demo-room")

    placed = result.photos[0]
    assert placed.status is LocateStatus.LOCATED_IN_CLAIMED
    assert placed.matched_model_id == "walk-fx"
    assert placed.pano_id.startswith("frame-")
    assert abs(int(placed.pano_id.split("-")[1]) - 6) <= 1  # around the 3 s frame
    assert "live" not in result.poses  # a video frame has no 3D pose


def test_sampling_caps_the_number_of_frames(tmp_path):
    clip = tmp_path / "walk.gif"
    walkthrough_clip(clip, seconds=6.0)
    assert len(sample_frames(clip, every_s=0.1, max_frames=20)) == 20


def test_unreadable_clip_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="could not read"):
        sample_frames(bad)

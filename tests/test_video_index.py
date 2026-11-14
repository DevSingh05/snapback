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


# --- review (#114): caps, budget, timestamps, bad fps, frames spread over the whole video --------


class FakeCapture:
    """A cv2.VideoCapture stand-in: `count` frames at `true_fps`, reporting `reported_fps`."""

    def __init__(self, count: int, true_fps: float, reported_fps: float) -> None:
        self.count, self.true_fps, self.reported_fps, self.at = count, true_fps, reported_fps, 0

    def isOpened(self) -> bool:  # noqa: N802 - cv2's name
        return True

    def get(self, prop):
        if prop == "fps":
            return self.reported_fps
        if prop == "count":
            return float(self.count)
        if prop == "msec":
            return 1000.0 * max(0, self.at - 1) / self.true_fps
        return 0.0

    def read(self):
        if self.at >= self.count:
            return False, None
        self.at += 1
        return True, np.full((48, 64, 3), self.at % 255, dtype=np.uint8)

    def release(self) -> None:
        pass


def fake_cv2(monkeypatch, count: int, true_fps: float, reported_fps: float) -> None:
    import sys
    import types

    module = types.SimpleNamespace(
        CAP_PROP_FPS="fps",
        CAP_PROP_FRAME_COUNT="count",
        CAP_PROP_POS_MSEC="msec",
        VideoCapture=lambda path: FakeCapture(count, true_fps, reported_fps),
    )
    monkeypatch.setitem(sys.modules, "cv2", module)


@pytest.mark.parametrize("reported", [30.0, 0.0, float("nan"), 1000.0])
def test_mp4_path_uses_the_video_clock_whatever_fps_it_reports(tmp_path, monkeypatch, reported):
    clip = tmp_path / "walk.mp4"
    clip.write_bytes(b"\x00" * 64)  # Pillow cannot read it, so the OpenCV path runs
    fake_cv2(monkeypatch, count=300, true_fps=30.0, reported_fps=reported)  # a 10 s video
    frames = sample_frames(clip, every_s=0.5)
    assert len(frames) == 20
    assert [round(t, 2) for t, _ in frames[:3]] == [0.0, 0.5, 1.0]


def test_a_long_video_is_refused_with_a_clear_error(tmp_path, monkeypatch):
    clip = tmp_path / "walk.mp4"
    clip.write_bytes(b"\x00" * 64)
    fake_cv2(monkeypatch, count=30 * 240, true_fps=30.0, reported_fps=30.0)  # 4 minutes
    with pytest.raises(ValueError, match="180 s"):
        sample_frames(clip)


def test_frames_spread_over_the_whole_video_when_the_cap_bites(tmp_path, monkeypatch):
    clip = tmp_path / "walk.mp4"
    clip.write_bytes(b"\x00" * 64)
    fake_cv2(monkeypatch, count=30 * 150, true_fps=30.0, reported_fps=30.0)  # 150 s
    frames = sample_frames(clip, every_s=0.5, max_frames=100)
    assert len(frames) <= 100
    assert frames[-1][0] > 140  # the last room is still in the index


def test_a_file_over_the_size_cap_is_refused(tmp_path, monkeypatch):
    import snapback.vision.locate.video_index as vi

    clip = tmp_path / "walk.mp4"
    clip.write_bytes(b"\x00" * 2048)
    monkeypatch.setattr(vi, "MAX_BYTES", 1024)
    with pytest.raises(ValueError, match="too large"):
        sample_frames(clip)


def test_reading_stops_at_the_time_budget(tmp_path, monkeypatch):
    import snapback.vision.locate.video_index as vi

    clip = tmp_path / "walk.mp4"
    clip.write_bytes(b"\x00" * 64)
    fake_cv2(monkeypatch, count=300, true_fps=30.0, reported_fps=30.0)
    monkeypatch.setattr(vi, "BUDGET_S", 0.0)
    with pytest.raises(ValueError, match="budget"):
        sample_frames(clip)

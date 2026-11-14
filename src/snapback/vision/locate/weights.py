"""Pinned model weights: what the locate pipeline downloads, and the sha256 it must match.

Every weight file is checked after loading, so a changed upstream file stops the run instead of
changing results silently. The matcher's weights go into LocateResult.thresholds_version.
`make prefetch-weights` downloads and checks all of them, so the demo machine never downloads
mid-run.

- DISK "depth" and LightGlue-DISK: kornia's Hugging Face repos (Apache-2.0), into torch's
  checkpoint folder.
- DINOv2 ViT-S/14: timm's Hugging Face repo at a fixed revision (Apache-2.0), into the
  Hugging Face cache.
"""

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path


class WeightMismatchError(RuntimeError):
    """A downloaded weight file is not the one this code was measured with."""


@dataclass(frozen=True)
class Weight:
    name: str
    file: str
    sha256: str


DISK_DEPTH = Weight(
    "disk-depth",
    "depth-save.pth",
    "9c2ee4ded238892dfa51569941372601e35e4a74aa6f84ea80053d2ab1c07abe",
)
LIGHTGLUE_DISK = Weight(
    "lightglue-disk",
    "disk_lightglue_v0-1_arxiv-pth",
    "b5b21d47ea24f2c5e501aec9c91b9716e4c8c3429a4dc1e615c133c4c9378335",
)
DINOV2_REPO_ID = "timm/vit_small_patch14_dinov2.lvd142m"
DINOV2_REVISION = "4610ca143709d58a633b6397a74412c2c3842454"
DINOV2 = Weight(
    "dinov2-vits14",
    "model.safetensors",
    "04d27f3400d059fc0cfd7d17dd1909a75bf3ea8fb3eeb48b97cb99e57ee20081",
)
MATCHER_WEIGHTS = (DISK_DEPTH, LIGHTGLUE_DISK)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check(weight: Weight, path: Path) -> str:
    """The file's sha256, or WeightMismatchError if it is missing or not the pinned file."""
    path = Path(path)
    if not path.is_file():
        raise WeightMismatchError(
            f"{weight.name}: {path.name} is missing; run make prefetch-weights"
        )
    found = sha256_of(path)
    if found != weight.sha256:
        raise WeightMismatchError(
            f"{weight.name}: sha256 {found[:12]} is not the pinned {weight.sha256[:12]}; "
            "delete the file and run make prefetch-weights"
        )
    return found


def tag(weights: tuple[Weight, ...] = MATCHER_WEIGHTS) -> str:
    """Short tag of the pinned weights, for thresholds_version."""
    return "+".join(f"{w.name}-{w.sha256[:8]}" for w in weights)


def checkpoint_dir() -> Path:  # pragma: no cover - needs torch
    import torch

    return Path(torch.hub.get_dir()) / "checkpoints"


def check_matcher_weights() -> None:  # pragma: no cover - needs torch
    for weight in MATCHER_WEIGHTS:
        check(weight, checkpoint_dir() / weight.file)


def dinov2_file() -> Path:  # pragma: no cover - needs huggingface_hub (vision extra)
    from huggingface_hub import hf_hub_download

    path = Path(hf_hub_download(DINOV2_REPO_ID, DINOV2.file, revision=DINOV2_REVISION))
    check(DINOV2, path)
    return path


def prefetch() -> int:  # pragma: no cover - downloads
    from snapback.vision.locate.verify import DiskLightGlue

    DiskLightGlue()  # downloads DISK and LightGlue if needed, then checks both hashes
    dinov2_file()
    for weight in (*MATCHER_WEIGHTS, DINOV2):
        print(f"{weight.name}: ok ({weight.sha256[:12]})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(prefetch())

"""Image embedders: one unit vector per image, for retrieval (locate) and photo memory.

- `Dinov2Embedder`: DINOv2 ViT-S/14 CLS token (Apache 2.0 code and weights). Needs the
  `vision` extra. The first use downloads the model through torch.hub (code from the
  facebookresearch/dinov2 GitHub repo at the commit pinned in `DINOV2_REPO`, weights from
  Meta's CDN) into ~/.cache/torch.
- `TinyEmbedder`: a few hundred numbers from colour and edge statistics, numpy only. Not a
  product model: it lets tests and CI exercise the index without torch.
"""

from typing import Protocol

import numpy as np
from PIL import Image, ImageOps

# Pinned so the code torch.hub runs never changes under us (main as of 2026-06-03, Apache-2.0).
DINOV2_REPO = "facebookresearch/dinov2:7764ea0f912e53c92e82eb78a2a1631e92725fc8"
# Preferred: the same ViT-S/14 DINOv2 weights through timm (CLS token, Apache-2.0).
TIMM_DINOV2 = "vit_small_patch14_dinov2.lvd142m"


class Embedder(Protocol):
    name: str

    def embed(self, image: Image.Image) -> np.ndarray: ...


def unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).flatten()
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


class TinyEmbedder:
    name = "tiny"

    def embed(self, image: Image.Image) -> np.ndarray:
        image = ImageOps.exif_transpose(image).convert("RGB")
        colour = np.asarray(image.resize((8, 8), Image.Resampling.BILINEAR), dtype=np.float32)
        grey = np.asarray(image.convert("L").resize((32, 32)), dtype=np.float32)
        gy, gx = np.gradient(grey)
        angle = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)
        weight = np.hypot(gx, gy)
        cells = []
        for rows in np.array_split(np.arange(32), 4):
            for cols in np.array_split(np.arange(32), 4):
                a = angle[np.ix_(rows, cols)].flatten()
                w = weight[np.ix_(rows, cols)].flatten()
                hist, _ = np.histogram(a, bins=8, range=(0, 1), weights=w)
                cells.append(hist)
        colour = (colour - colour.mean()) / (colour.std() + 1e-6)
        edges = np.concatenate(cells)
        edges = edges / (np.linalg.norm(edges) + 1e-6)
        return unit(np.concatenate([colour.flatten() / 8.0, edges]))


class Dinov2Embedder:  # pragma: no cover - needs torch and a one-time download
    name = "dinov2_vits14"
    SIZE = 224
    MEAN = (0.485, 0.456, 0.406)
    STD = (0.229, 0.224, 0.225)

    def __init__(self, device: str | None = None) -> None:
        import torch

        self._torch = torch
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = device
        try:
            # timm builds the network from its own (version-locked) code and fetches only the
            # weights (Apache-2.0) from Hugging Face; no repository code is downloaded or run.
            import timm

            model = timm.create_model(
                TIMM_DINOV2, pretrained=True, num_classes=0, img_size=self.SIZE
            )
        except ImportError:
            model = torch.hub.load(DINOV2_REPO, self.name, trust_repo=True)
        self._model = model.eval().to(device)

    def _tensor(self, image: Image.Image):
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = image.resize((self.SIZE, self.SIZE), Image.Resampling.BICUBIC)
        pixels = np.asarray(image, dtype=np.float32) / 255.0
        pixels = (pixels - np.array(self.MEAN, dtype=np.float32)) / np.array(
            self.STD, dtype=np.float32
        )
        return self._torch.from_numpy(pixels.transpose(2, 0, 1).copy())

    def embed_many(self, images: list[Image.Image], batch: int = 32) -> np.ndarray:
        out = []
        with self._torch.inference_mode():
            for start in range(0, len(images), batch):
                stack = self._torch.stack([self._tensor(i) for i in images[start : start + batch]])
                features = self._model(stack.to(self.device)).float().cpu().numpy()
                out.extend(unit(row) for row in features)
        return np.stack(out)

    def embed(self, image: Image.Image) -> np.ndarray:
        return self.embed_many([image])[0]

"""The recapture check on one reply photo, behind RECAPTURE_MODEL=on.

Off (the default, or no model file): every reply gets model_version "off", score 0 and never
blocks, so the product behaves exactly as without the model.
"""

import os
from pathlib import Path

from PIL import Image

from snapback.contracts import RecaptureLabel, RecaptureResult
from snapback.vision.recapture.features import features
from snapback.vision.recapture.model import RecaptureModel

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL = REPO_ROOT / "data" / "recapture" / "v0.json"


def enabled() -> bool:
    return os.environ.get("RECAPTURE_MODEL", "off").strip().lower() == "on"


class RecaptureDetector:
    def __init__(self, model: RecaptureModel | None) -> None:
        self.model = model

    @classmethod
    def from_file(cls, path: Path = DEFAULT_MODEL) -> "RecaptureDetector":
        return cls(RecaptureModel.load(path) if path.is_file() else None)

    def check(self, photo_id: str, image: Image.Image) -> RecaptureResult:
        if self.model is None or not enabled():
            return RecaptureResult(
                photo_id=photo_id,
                label=RecaptureLabel.UNKNOWN,
                score=0.0,
                blocks_pass=False,
                model_version="off",
            )
        vector = features(image)
        score = self.model.score_vector(vector)
        blocks = score > self.model.threshold
        return RecaptureResult(
            photo_id=photo_id,
            label=self.model.attack_label(vector) if blocks else RecaptureLabel.GENUINE,
            score=round(min(1.0, max(0.0, score)), 4),
            blocks_pass=blocks,
            model_version=self.model.version,
        )

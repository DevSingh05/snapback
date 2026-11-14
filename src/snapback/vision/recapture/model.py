"""Recapture model: softmax regression over the image signals, Platt-calibrated, one frozen
threshold. Numpy only; small enough to retrain in seconds (learning-v2 L6: deleting a case means
retraining without it).

The calibrated score is the probability a photo is NOT a fresh photo of the room. A score over
the threshold only blocks a pass (ask for a new photo); it never accuses anyone.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from snapback.contracts import RecaptureLabel
from snapback.vision.recapture.features import FEATURE_NAMES, features

CLASSES = (
    RecaptureLabel.GENUINE,
    RecaptureLabel.SCREEN,
    RecaptureLabel.PRINT,
    RecaptureLabel.PASTE,
)


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_softmax(
    x: np.ndarray, y: np.ndarray, classes: int, l2: float = 1e-2, steps: int = 800, lr: float = 0.5
) -> np.ndarray:
    """Weights (features + 1, classes) by gradient descent on the mean cross-entropy."""
    xb = np.c_[x, np.ones(len(x))]
    w = np.zeros((xb.shape[1], classes))
    onehot = np.eye(classes)[y]
    # Weight classes evenly: attacks outnumber genuine photos three to one.
    counts = np.bincount(y, minlength=classes).astype(float)
    sample_w = (len(y) / (classes * np.maximum(counts, 1)))[y][:, None]
    for _ in range(steps):
        p = _softmax(xb @ w)
        grad = (
            xb.T @ ((p - onehot) * sample_w) / len(x) + l2 * np.r_[w[:-1], np.zeros((1, classes))]
        )
        w -= lr * grad
    return w


def fit_platt(
    raw: np.ndarray, target: np.ndarray, steps: int = 2000, lr: float = 0.1
) -> tuple[float, float]:
    """a, b with P(target) = sigmoid(a * raw + b)."""
    a, b = 1.0, 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(a * raw + b)))
        a -= lr * float(((p - target) * raw).mean())
        b -= lr * float((p - target).mean())
    return a, b


@dataclass
class RecaptureModel:
    version: str
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray  # (features + 1, classes)
    platt: tuple[float, float]
    threshold: float
    synthetic_only: bool
    meta: dict = field(default_factory=dict)

    def _logits(self, vector: np.ndarray) -> np.ndarray:
        x = (vector - self.mean) / self.scale
        return np.r_[x, 1.0] @ self.weights

    def raw(self, vector: np.ndarray) -> float:
        """Log-odds of not genuine, before calibration."""
        p = _softmax(self._logits(vector)[None])[0]
        return float(np.log((1 - p[0]) + 1e-9) - np.log(p[0] + 1e-9))

    def score_vector(self, vector: np.ndarray) -> float:
        a, b = self.platt
        return float(1 / (1 + np.exp(-(a * self.raw(vector) + b))))

    def score(self, image: Image.Image) -> float:
        return self.score_vector(features(image))

    def attack_label(self, vector: np.ndarray) -> RecaptureLabel:
        logits = self._logits(vector)
        return CLASSES[1 + int(np.argmax(logits[1:]))]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": self.version,
                    "features": list(FEATURE_NAMES),
                    "classes": [c.value for c in CLASSES],
                    "mean": self.mean.tolist(),
                    "scale": self.scale.tolist(),
                    "weights": self.weights.tolist(),
                    "platt": list(self.platt),
                    "threshold": self.threshold,
                    "synthetic_only": self.synthetic_only,
                    "meta": self.meta,
                },
                indent=1,
            )
        )

    @classmethod
    def load(cls, path: Path) -> "RecaptureModel":
        data = json.loads(path.read_text())
        if data["features"] != list(FEATURE_NAMES):
            raise ValueError("model was trained on a different feature set; retrain it")
        return cls(
            version=data["version"],
            mean=np.array(data["mean"]),
            scale=np.array(data["scale"]),
            weights=np.array(data["weights"]),
            platt=tuple(data["platt"]),
            threshold=float(data["threshold"]),
            synthetic_only=bool(data["synthetic_only"]),
            meta=data.get("meta", {}),
        )

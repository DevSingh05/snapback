"""Recapture detector (V4): is a reply a fresh photo of the room, or a photo of a screen, a
printout, or a code pasted on digitally? It can only block a pass, never accuse.
"""

from snapback.vision.recapture.detector import DEFAULT_MODEL, RecaptureDetector, enabled
from snapback.vision.recapture.features import FEATURE_NAMES, features
from snapback.vision.recapture.model import CLASSES, RecaptureModel
from snapback.vision.recapture.train import TrainingRow, TrainReport, auroc, read_manifest, train

__all__ = [
    "CLASSES",
    "DEFAULT_MODEL",
    "FEATURE_NAMES",
    "RecaptureDetector",
    "RecaptureModel",
    "TrainReport",
    "TrainingRow",
    "auroc",
    "enabled",
    "features",
    "read_manifest",
    "train",
]

"""The frozen locate thresholds, and the version tag that LocateResult carries."""

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

THRESHOLDS_FILE = Path(__file__).with_name("thresholds.toml")


@dataclass(frozen=True)
class Thresholds:
    top_k: int
    top_k_claimed: int
    min_inliers: int
    min_inlier_ratio: float
    ransac_px: float
    stop_at_inliers: int
    elsewhere_min_inliers: int
    elsewhere_min_spread: float
    ambiguity_ratio: float
    claimed_min_spread: float
    default_hfov_deg: float
    spots_top_n: int
    spots_overlap_deg: float
    version: str
    flip_search: bool = True


def load_thresholds(path: Path = THRESHOLDS_FILE) -> Thresholds:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode())
    verify_cfg = data["verify"]
    if verify_cfg["elsewhere_min_inliers"] < verify_cfg["min_inliers"]:
        raise ValueError("elsewhere_min_inliers must not be below min_inliers")
    if not 0.0 <= verify_cfg["claimed_min_spread"] <= verify_cfg["elsewhere_min_spread"]:
        raise ValueError("claimed_min_spread must be between 0 and elsewhere_min_spread")
    if verify_cfg["ambiguity_ratio"] <= 1.0:
        raise ValueError("ambiguity_ratio must be greater than 1.0")
    return Thresholds(
        top_k=data["retrieve"]["top_k"],
        top_k_claimed=data["retrieve"]["top_k_claimed"],
        min_inliers=data["verify"]["min_inliers"],
        min_inlier_ratio=data["verify"]["min_inlier_ratio"],
        ransac_px=data["verify"]["ransac_px"],
        stop_at_inliers=data["verify"]["stop_at_inliers"],
        elsewhere_min_inliers=data["verify"]["elsewhere_min_inliers"],
        elsewhere_min_spread=data["verify"]["elsewhere_min_spread"],
        ambiguity_ratio=data["verify"]["ambiguity_ratio"],
        claimed_min_spread=data["verify"]["claimed_min_spread"],
        default_hfov_deg=data["pose"]["default_hfov_deg"],
        spots_top_n=data["spots"]["top_n"],
        spots_overlap_deg=data["spots"]["overlap_deg"],
        version="thresholds-" + hashlib.sha256(raw).hexdigest()[:12],
        flip_search=bool(data["verify"].get("flip_search", True)),
    )

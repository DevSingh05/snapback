"""Where data/ is. A relative SNAPBACK_DATA_DIR means relative to the repo, not to wherever a
command happens to run (purging from apps/web must still purge the repo's data/)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_data_dir(data_dir: Path | str) -> Path:
    path = Path(data_dir)
    return path if path.is_absolute() else REPO_ROOT / path

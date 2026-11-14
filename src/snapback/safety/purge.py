"""`make purge`: delete every sponsor cache, upload and the memory DB under data/.

The sponsor terms say all copies, caches and derivatives are deleted when the event period ends
(Sun 16:00). This empties the data folder and keeps the folder itself (and a `.gitkeep`).
"""

import shutil
from pathlib import Path

from snapback.safety import paths

KEEP = {".gitkeep"}


class PurgeRefusedError(RuntimeError):
    pass


def purge(data_dir: Path) -> int:
    """Remove everything inside `data_dir`. Returns how many top-level entries went."""
    data_dir = paths.resolve_data_dir(data_dir).resolve()
    if data_dir.name != "data":
        raise PurgeRefusedError(f"refusing to purge {data_dir}: only a folder named data/")
    if not data_dir.is_dir():
        raise FileNotFoundError(f"nothing to purge: {data_dir} does not exist")
    removed = 0
    for entry in data_dir.iterdir():
        if entry.name in KEEP:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed += 1
    return removed

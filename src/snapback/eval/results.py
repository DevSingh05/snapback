"""results.csv: one row per (condition, metric), read by the Lab panel (T6) and the API.

Columns are fixed: condition,metric,k,n,rate,ci_low,ci_high,frozen_at. Lines starting with #
are comments (the first one says FIXTURE or LIVE). Rates and bounds have four decimals. One
comment line, `# meta: key=value ...`, records how the run was made (the split), so the gate
can refuse to compare runs made differently. The file is written to a temporary name and moved
into place, so the API never serves half a file.
"""

import csv
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from pydantic import BaseModel

from snapback.eval.stats import wilson

META_PREFIX = "# meta: "

RESULTS_COLUMNS = ("condition", "metric", "k", "n", "rate", "ci_low", "ci_high", "frozen_at")


class ResultRow(BaseModel):
    condition: str
    metric: str
    k: int
    n: int
    rate: float
    ci_low: float
    ci_high: float
    frozen_at: str

    @classmethod
    def measure(cls, condition: str, metric: str, k: int, n: int, frozen_at: str) -> "ResultRow":
        low, high = wilson(k, n)
        return cls(
            condition=condition,
            metric=metric,
            k=k,
            n=n,
            rate=round(k / n, 4),
            ci_low=round(low, 4),
            ci_high=round(high, 4),
            frozen_at=frozen_at,
        )


def write_results(
    rows: Iterable[ResultRow],
    path: Path,
    comment: str | None = None,
    meta: Mapping[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", newline="") as handle:
            _write(handle, rows, comment, meta)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _write(handle, rows, comment, meta) -> None:
    if comment:
        for line in comment.splitlines():
            handle.write(f"# {line}\n")
    if meta:
        handle.write(META_PREFIX + " ".join(f"{k}={v}" for k, v in meta.items()) + "\n")
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(RESULTS_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.condition,
                row.metric,
                row.k,
                row.n,
                f"{row.rate:.4f}",
                f"{row.ci_low:.4f}",
                f"{row.ci_high:.4f}",
                row.frozen_at,
            ]
        )


def read_meta(path: Path) -> dict[str, str]:
    for line in path.read_text().splitlines():
        if line.startswith(META_PREFIX):
            pairs = (item.partition("=") for item in line[len(META_PREFIX) :].split())
            return {key: value for key, _, value in pairs if key}
    return {}


def read_results(path: Path) -> list[ResultRow]:
    lines = [line for line in path.read_text().splitlines() if not line.startswith("#")]
    reader = csv.DictReader(lines)
    return [ResultRow.model_validate(row) for row in reader]

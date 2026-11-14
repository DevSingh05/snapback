"""The eval harness's results file, served read-only for the Lab panel (issue #69).

`make eval` (lane V) writes one small CSV of aggregate numbers: how often each condition
caught what it should, with n and an interval. It holds no case data, so the route is public.
That makes this guard matter more: this module reads that one file and nothing else. The
path comes from settings, never from a request, and the file is handed out only if it is the
agreed CSV, header and every row. If the setting is pointed at some other file by mistake,
or the file is caught half written, nothing from it leaves the server.
"""

import csv
from pathlib import Path

# The contract, shared with lane V (who writes it) and lane T (who draws it). The fixture is
# fixtures/contracts/results_sample.csv. Lines starting with "#" are comments, and the first
# one says FIXTURE or LIVE.
RESULTS_COLUMNS = ("condition", "metric", "k", "n", "rate", "ci_low", "ci_high", "frozen_at")
# The measured ad batch (`make eval-ads`): one row per ad type and verdict, with a miss flag.
ADS_COLUMNS = (
    "ad_type",
    "origin",
    "expected",
    "got",
    "k",
    "n",
    "rate",
    "ci_low",
    "ci_high",
    "miss",
    "frozen_at",
)
MAX_RESULTS_BYTES = 1024 * 1024


class NotTheAgreedCsv(Exception):
    """There is a file at the results path, but it is not the eval results CSV."""


def read_results(path: Path, columns: tuple[str, ...] = RESULTS_COLUMNS) -> bytes | None:
    """The results file exactly as written, or None if there is no file yet.

    `columns` is the agreed header: the eval results by default, or `ADS_COLUMNS`.
    """
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_RESULTS_BYTES:
        raise NotTheAgreedCsv(path)
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise NotTheAgreedCsv(path) from None

    rows = csv.reader(line for line in lines if line.strip() and not line.startswith("#"))
    header = next(rows, [])
    if tuple(column.strip() for column in header) != columns:
        raise NotTheAgreedCsv(path)
    # Every row has the agreed fields, and the counts are counts. A file caught half written
    # ends in a short row and is refused, as is any other CSV that borrowed the header.
    for row in rows:
        if len(row) != len(columns) or not (
            row[columns.index("k")].isdigit() and row[columns.index("n")].isdigit()
        ):
            raise NotTheAgreedCsv(path)
    return raw

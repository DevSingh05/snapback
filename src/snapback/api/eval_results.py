"""The eval harness's results file, served read-only for the Lab panel (issue #69).

`make eval` (lane V) writes one small CSV of aggregate numbers: how often each condition
caught what it should, with n and an interval. This module reads that one file and nothing
else. The path comes from settings, never from a request, and the file is handed out only if
it is the agreed CSV: if the setting is pointed at some other file by mistake, nothing from
that file leaves the server.
"""

from pathlib import Path

# The contract, shared with lane V (who writes it) and lane T (who draws it). The fixture is
# fixtures/contracts/results_sample.csv. Lines starting with "#" are comments, and the first
# one says FIXTURE or LIVE.
RESULTS_COLUMNS = ("condition", "metric", "k", "n", "rate", "ci_low", "ci_high", "frozen_at")
MAX_RESULTS_BYTES = 1024 * 1024


class NotTheAgreedCsv(Exception):
    """There is a file at the results path, but it is not the eval results CSV."""


def read_results(path: Path) -> bytes | None:
    """The results file exactly as written, or None if there is no file yet."""
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_RESULTS_BYTES:
        raise NotTheAgreedCsv(path)
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise NotTheAgreedCsv(path) from None

    rows = (line for line in lines if line.strip() and not line.startswith("#"))
    header = next(rows, "")
    if tuple(column.strip() for column in header.split(",")) != RESULTS_COLUMNS:
        raise NotTheAgreedCsv(path)
    return raw

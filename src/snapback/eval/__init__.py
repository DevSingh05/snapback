"""Eval harness (V6): scores the case bank, writes every number we quote, gates CI.

No number appears in the pitch unless this package produced it, with n shown. Run it with
`uv run python -m snapback.eval`; `--help` lists the options.
"""

from snapback.eval.bank import BankCase, CaseKind, load_bank
from snapback.eval.harness import check_injections, check_regression, conditions, evaluate
from snapback.eval.results import RESULTS_COLUMNS, ResultRow, read_results, write_results
from snapback.eval.stats import wilson

__all__ = [
    "RESULTS_COLUMNS",
    "BankCase",
    "CaseKind",
    "ResultRow",
    "check_injections",
    "check_regression",
    "conditions",
    "evaluate",
    "load_bank",
    "read_results",
    "wilson",
    "write_results",
]

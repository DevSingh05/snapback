"""Safety (lane D, module 12): per-renter limits, the delete command and `make purge`.

What we read, where it goes and how long we keep it is in DATA_USE.md at the repo root.
"""

from snapback.safety.delete import DeleteReport, delete_case, delete_renter
from snapback.safety.limits import RenterLimits, check_limit
from snapback.safety.purge import PurgeRefusedError, purge
from snapback.safety.store import SafetyStore

__all__ = [
    "DeleteReport",
    "PurgeRefusedError",
    "RenterLimits",
    "SafetyStore",
    "check_limit",
    "delete_case",
    "delete_renter",
    "purge",
]

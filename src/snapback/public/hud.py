"""HUD Small Area Fair Market Rent: the typical rent for a ZIP and bedroom count.

HUD publishes one rent per ZIP and bedroom count, every year, as public domain data. It is a
40th percentile gross rent, a floor-ish baseline: it can catch a rent far BELOW the area and
never calls a rent too high. `fixtures/public/hud_safmr_tx.csv` holds the Texas rows
(built by `scripts/build_hud_safmr.py` from the FY2027 spreadsheet). Offline; no network.
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

from snapback.contracts import PriceResult, PriceStatus

TABLE = Path(__file__).resolve().parents[3] / "fixtures" / "public" / "hud_safmr_tx.csv"
MAX_BEDS = 4  # HUD publishes 0 to 4 bedrooms; a larger home is compared with the 4 bedroom rent
SOURCE_NAME = "HUD"
# A ZIP counts only right after the state, so a rent or a phone number is never read as one.
_ZIP = re.compile(r"\b(?:TX|Texas)\.?,?\s+(\d{5})(?:-\d{4})?\b", re.I)


@lru_cache
def _table() -> dict[str, tuple[int, ...]]:
    with TABLE.open(newline="", encoding="utf-8") as fh:
        return {
            row["zip"]: tuple(int(row[f"br{n}"]) for n in range(MAX_BEDS + 1))
            for row in csv.DictReader(fh)
        }


def vintage() -> str:
    with TABLE.open(newline="", encoding="utf-8") as fh:
        return next(csv.DictReader(fh))["vintage"]


def below_ratio() -> float:
    from snapback.settings import get_settings

    return get_settings().snapback_hud_below_ratio


def zip_in(text: str) -> str | None:
    found = _ZIP.search(text or "")
    return found.group(1) if found else None


def typical_rent(zip_code: str | None, beds: int | None) -> int | None:
    """HUD's rent for this ZIP and size, or None (not a Texas ZIP in the table, or no size)."""
    if not zip_code or beds is None or beds < 0:
        return None
    row = _table().get(zip_code)
    return row[min(beds, MAX_BEDS)] if row else None


def check_price(
    listed_rent: int | None,
    beds: int | None,
    zip_code: str | None,
    *,
    ratio: float | None = None,
) -> PriceResult | None:
    """The ad's rent against HUD's. None when HUD cannot answer: nothing was compared.

    Below the ratio is BELOW_RANGE, which sets `price_flag` (HOLD, never DONT_PAY on its own).
    """
    baseline = typical_rent(zip_code, beds)
    if listed_rent is None or baseline is None or beds is None:
        return None
    cutoff = below_ratio() if ratio is None else ratio
    below = listed_rent < cutoff * baseline
    return PriceResult(
        status=PriceStatus.BELOW_RANGE if below else PriceStatus.WITHIN_RANGE,
        listed_rent=listed_rent,
        baseline_source="hud_safmr",
        baseline_rent=baseline,
        baseline_zip=zip_code,
        baseline_beds=min(beds, MAX_BEDS),
    )

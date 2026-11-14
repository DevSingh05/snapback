"""What the agent remembers about one renter's session (Hearth parity), kept per case.

The keys are fixed in code: a rejected walk-up, a parking need, a lower budget, places to stop
showing. A renter's words never become a preference, and a model sees only which keys are set
(and how many places are avoided), never an id. Applying a preference is code: it narrows the
brief or the list, so a place the renter rejected cannot come back."""

from __future__ import annotations

from snapback.contracts import CasePreferences, PreferencesUpdate, RenterBrief

MAX_AVOIDED = 50

# The only memory facts a chooser may be shown: yes/no, and a count for the avoided places.
MEMORY_FACT_KEYS = frozenset(
    {"remembers_no_walkup", "remembers_parking", "remembers_max_rent", "remembers_avoided"}
)


def merge(current: CasePreferences, update: PreferencesUpdate) -> CasePreferences:
    """The new memory. A lower budget wins; an avoided place is added once."""
    out = current.model_copy(deep=True)
    if update.no_walkup is not None:
        out.no_walkup = update.no_walkup
    if update.needs_parking is not None:
        out.needs_parking = update.needs_parking
    if update.max_rent is not None:
        out.max_rent = (
            update.max_rent if out.max_rent is None else min(out.max_rent, update.max_rent)
        )
    if update.prefer_scans is not None:
        out.prefer_scans = update.prefer_scans
    pid = update.avoid_property_id
    if pid and pid not in out.avoid_property_ids and len(out.avoid_property_ids) < MAX_AVOIDED:
        out.avoid_property_ids.append(pid)
    return out


def keys_of(prefs: CasePreferences | None) -> list[str]:
    """The preference keys that are set, for the response and for the model's facts."""
    if prefs is None:
        return []
    out = []
    if prefs.no_walkup:
        out.append("no_walkup")
    if prefs.needs_parking:
        out.append("needs_parking")
    if prefs.max_rent is not None:
        out.append("max_rent")
    if prefs.prefer_scans:
        out.append("prefer_scans")
    if prefs.avoid_property_ids:
        out.append("avoid_property_id")
    return out


def facts_of(prefs: CasePreferences | None) -> dict[str, bool | int]:
    """Yes/no and a count: no id, no amount."""
    p = prefs or CasePreferences()
    return {
        "remembers_no_walkup": p.no_walkup,
        "remembers_parking": p.needs_parking,
        "remembers_max_rent": p.max_rent is not None,
        "remembers_avoided": len(p.avoid_property_ids),
    }


def apply_to_brief(brief: RenterBrief, prefs: CasePreferences | None) -> RenterBrief:
    """The brief with what the renter already rejected folded in. Only ever narrows it."""
    if prefs is None:
        return brief
    update: dict[str, object] = {}
    if prefs.no_walkup:
        update["needs_no_walkup"] = True
    if prefs.needs_parking:
        update["needs_parking"] = True
    if prefs.max_rent is not None:
        cap = prefs.max_rent
        update["max_rent_month"] = (
            cap if brief.max_rent_month is None else min(brief.max_rent_month, cap)
        )
    return brief.model_copy(update=update) if update else brief

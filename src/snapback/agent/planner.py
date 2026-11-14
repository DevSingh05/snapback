"""The evidence-driven plan (A24): which check to run next, from options code wrote.

After the first choice (which kinds of check) the case enters a plan. Code lists five options
in a fixed order and works out, from evidence it already holds, which of them can run:

- `home record`: the home's own record (rent band, who is on record, sale history);
- `listing brokerage`: the listing office behind an ACTIVE for-sale match;
- `TREC license`: the license the ad names, looked up with the state (D10);
- `owner of record`: the public owner file (D12, not merged yet: it shows as skipped until a
  module offers it);
- `report pack`: the closing step, open once every other check has run or been skipped.

An option whose evidence is missing is not offered; it is shown as skipped, with the reason.

Who picks is the chooser's business (the code policy, or a model behind the same list). What
the pick changes is the ORDER of the checks, never which of them run: every option that can run
does. So the evidence at the end of the plan, and the verdict `decide()` draws from it, is the
same whoever picked. The reasons below are code-written; a model's own reason replaces one on
the trace, after `clean_reason`, and never reaches a card.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from snapback.contracts import (
    AuthorityResult,
    ForSaleMatch,
    ForSaleStatus,
    LicenseResult,
    ModuleEvidence,
    PriceResult,
)


class PlanKind(StrEnum):
    RECORD = "home record"
    BROKERAGE = "listing brokerage"
    LICENSE = "TREC license"
    OWNER = "owner of record"
    REPORT = "report pack"


ORDER = (PlanKind.RECORD, PlanKind.BROKERAGE, PlanKind.LICENSE, PlanKind.OWNER, PlanKind.REPORT)

# The words live in card/strings.py (`plan.pick.<key>`, `plan.skip.<key>`); here are the keys.
PICK_KEY: dict[PlanKind, str] = {
    PlanKind.RECORD: "plan.pick.record",
    PlanKind.BROKERAGE: "plan.pick.brokerage",
    PlanKind.LICENSE: "plan.pick.license",
    PlanKind.OWNER: "plan.pick.owner",
    PlanKind.REPORT: "plan.pick.report",
}


@dataclass(frozen=True)
class Skipped:
    kind: PlanKind
    reason: str  # a `plan.skip.*` key


class Plan:
    """The options for one case, what each can run on, and what has run.

    The lookups are the ones the session used to make all at once when the first choice was
    applied. They are made once, here, and kept; only the moment and the order changed.
    """

    def __init__(self, modules: Any, case_id: str) -> None:
        self._price: PriceResult | None = modules.price(case_id)
        self._authority: AuthorityResult | None = modules.authority(case_id)
        self._for_sale: ForSaleMatch | None = modules.for_sale(case_id)
        # Optional lookups: a Modules implementation may offer these two. Until one does, the
        # option is shown as skipped. Nothing here imports the code that will provide them.
        license_fn = getattr(modules, "license", None)
        owner_fn = getattr(modules, "owner_of_record", None)
        self._license_offered = callable(license_fn)
        self._owner_offered = callable(owner_fn)
        self._license: LicenseResult | None = license_fn(case_id) if callable(license_fn) else None
        self._owner: object | None = owner_fn(case_id) if callable(owner_fn) else None
        self.ran: list[PlanKind] = []

    # --- what each option can run on -------------------------------------------------------

    @property
    def _active_sale(self) -> bool:
        return self._for_sale is not None and self._for_sale.status is ForSaleStatus.ACTIVE

    @property
    def _record_sale(self) -> ForSaleMatch | None:
        """A for-sale lookup that is not an ACTIVE listing is part of the home's own record."""
        return self._for_sale if self._for_sale is not None and not self._active_sale else None

    def _has_record(self) -> bool:
        return bool(self._price or self._authority or self._record_sale)

    def _skip_reason(self, kind: PlanKind) -> str | None:
        """The `plan.skip.*` key for why `kind` cannot run now; None when it can."""
        if kind is PlanKind.RECORD:
            return None if self._has_record() else "plan.skip.record"
        if kind is PlanKind.BROKERAGE:
            return None if self._active_sale else "plan.skip.brokerage"
        if kind is PlanKind.LICENSE:
            if not self._license_offered:
                return "plan.skip.license_off"
            return None if self._license is not None else "plan.skip.license_none"
        if kind is PlanKind.OWNER:
            if not self._owner_offered:
                return "plan.skip.owner_off"
            return None if self._owner is not None else "plan.skip.owner_none"
        # The report pack closes the plan: after everything else, and only if something ran.
        if any(self._pending(other) for other in ORDER if other is not PlanKind.REPORT):
            return "report_wait"
        return None if self.ran else "report_empty"

    def _pending(self, kind: PlanKind) -> bool:
        return kind not in self.ran and self._skip_reason(kind) is None

    # --- reading the plan ------------------------------------------------------------------

    def open_options(self) -> list[PlanKind]:
        """The options that can run now, in the fixed order."""
        return [kind for kind in ORDER if self._pending(kind)]

    def skipped(self) -> list[Skipped]:
        """The check options that cannot run, with why. The report pack is not listed: it is
        simply not open until the rest are done."""
        out = []
        for kind in ORDER[:-1]:
            reason = self._skip_reason(kind)
            if reason is not None and kind not in self.ran:
                out.append(Skipped(kind, reason))
        return out

    def facts(self) -> dict[str, bool | int | str]:
        """Derived facts for the chooser: yes/no and counts. No rows, names or images."""
        return {
            "home_record_found": self._has_record(),
            "for_sale_listing_active": self._active_sale,
            "ad_names_a_license": self._license is not None,
            "owner_on_public_record": self._owner is not None,
            "checks_run": len(self.ran),
            "checks_left": len(self.open_options()),
        }

    # --- running an option -----------------------------------------------------------------

    def run(self, kind: PlanKind) -> dict[str, object]:
        """Mark `kind` run and return the evidence fields it contributes."""
        if kind not in self.open_options():
            raise ValueError(f"{kind.value!r} cannot run now")
        self.ran.append(kind)
        if kind is PlanKind.RECORD:
            update: dict[str, object] = {"price": self._price, "authority": self._authority}
            if self._record_sale is not None:
                update["for_sale"] = self._record_sale
            return update
        if kind is PlanKind.BROKERAGE:
            return {"for_sale": self._for_sale}
        if kind is PlanKind.LICENSE:
            return {"license": self._license}
        if kind is PlanKind.OWNER and "owner" in ModuleEvidence.model_fields:
            # The owner file's evidence field arrives with D12. Until it does, an owner module
            # can still be offered and run; there is just nothing on ModuleEvidence to hold it.
            return {"owner": self._owner}
        return {}

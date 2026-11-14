"""A10 (issue #97): join lane D's adapters to the agent.

A check runs on the building's own record: the CoStar record (D1) and the for-sale lookup
(D7) feed lane A's price, unit and contact rules. The twin (locate) and the challenge are
still stand-ins until lanes V and D land them (V2, D3), so a joined case is honest about
which is which: `record_source` says where the record parts came from, and the card as a
whole stays FIXTURE while any stand-in is in it.

Nothing here logs or returns a value from a record. The rules turn it into statuses.
"""

import threading
from pathlib import Path
from typing import Protocol

from snapback.agent.intake import Listing
from snapback.agent.modules import ChallengeOutcome, FixtureModules
from snapback.agent.rules import check_price
from snapback.agent.rules.contact import check_authority
from snapback.agent.scope import ListingScope
from snapback.contracts import (
    AuthorityResult,
    DataSource,
    FloorPlanCandidate,
    ForSaleMatch,
    LocateResult,
    PriceResult,
    PropertyRecord,
    RuleHit,
    SpotCandidate,
    SpotRanking,
)


class KitMissing(Exception):
    """The record was asked for and the kit is not on this machine."""

    def __init__(self) -> None:
        super().__init__(
            "The CoStar kit is not on this server, so there is no record to read. "
            "See the README, 'Get the CoStar kit', or run with SNAPBACK_DATA_SOURCE=fixture."
        )


class Lookups(Protocol):
    """What the join needs from lane D."""

    def record(self, property_id: str) -> PropertyRecord | None:
        """The record for our id, or None if we hold none."""
        ...

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        """Is the home in the listing for sale or just rented? None means not looked up."""
        ...


class KitLookups:
    """Lane D's adapters. The kit is parsed once and kept for the life of the process."""

    def __init__(self, source: DataSource, kit_dir: Path | None = None) -> None:
        self.source = source
        self._kit_dir = kit_dir
        self._records: dict[str, PropertyRecord] | None = None
        self._lock = threading.Lock()

    def record(self, property_id: str) -> PropertyRecord | None:
        from snapback.adapters import costar_jsonl

        with self._lock:
            if self._records is None:
                try:
                    self._records = costar_jsonl.load_records(self.source, self._kit_dir)
                except costar_jsonl.KitNotFoundError:
                    raise KitMissing from None
            return self._records.get(property_id)

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        try:
            from snapback.adapters import costar_residential
        except ImportError:
            return None  # lane D's lookup (D7) is not here: nothing was looked up
        return costar_residential.for_sale_lookup(listing_text, self.source, self._kit_dir)


class JoinedModules:
    """What the agent calls: the record parts from lane D, the rest from the stand-in."""

    def __init__(
        self,
        *,
        stand_in: FixtureModules,
        listing: Listing,
        record: PropertyRecord | None,
        for_sale: ForSaleMatch | None,
        salt: str,
        record_source: DataSource | None,
    ) -> None:
        self._stand_in = stand_in
        self._listing = listing
        self._record = record
        self._for_sale = for_sale
        self._salt = salt
        self._record_source = record_source

    # --- from the listing and the record ---------------------------------------------------

    def listing_scope(self, case_id: str) -> ListingScope:
        return self._listing.scope

    def rules(self, case_id: str) -> list[RuleHit]:
        return list(self._listing.rule_hits)

    def price(self, case_id: str) -> PriceResult | None:
        listing = self._listing
        return check_price(listing.listed_rent, self._record, beds=listing.beds, unit=listing.unit)

    def authority(self, case_id: str) -> AuthorityResult | None:
        return check_authority(self._listing.contacts, self._record, self._salt)

    def for_sale(self, case_id: str) -> ForSaleMatch | None:
        return self._for_sale

    def record_source(self, case_id: str) -> DataSource | None:
        """Where the record parts came from, or None if there are none."""
        if self._record is None and self._for_sale is None:
            return None
        return self._record_source

    # --- the twin and the challenge: stand-ins until V2 and D3 land --------------------------

    def has_twin(self, case_id: str) -> bool:
        # The one thing the stand-in may not decide: a real building with no 3D model has no
        # twin, and must not be handed the stand-in's placed photos.
        if self._record is not None and not self._record.model_ids:
            return False
        return self._stand_in.has_twin(case_id)

    def photo_count(self, case_id: str) -> int:
        return self._stand_in.photo_count(case_id)

    def floor_plans(self, case_id: str) -> list[FloorPlanCandidate]:
        return self._stand_in.floor_plans(case_id)

    def locate(self, case_id: str) -> LocateResult | None:
        if not self.has_twin(case_id):
            return None
        return self._stand_in.locate(case_id)

    def spot_ranking(self, case_id: str, model_id: str | None) -> SpotRanking | None:
        return self._stand_in.spot_ranking(case_id, model_id)

    def new_code(self, case_id: str) -> str:
        return self._stand_in.new_code(case_id)

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        return self._stand_in.challenge(case_id, spot, code, text, attempt)

    @property
    def sent_messages(self) -> list[str]:
        return self._stand_in.sent_messages

"""A10 (issue #97): join lane D's adapters to the agent.

A check runs on the building's own record: the CoStar record (D1) and the for-sale lookup
(D7) feed lane A's price, unit and contact rules.

The twin (locate) and the challenge are still stand-ins until lanes V and D land them (V2,
D3), and a stand-in is fixture data. So they are used in a fixture case only. A live case, or
any case on a live record, has no twin and no challenge: nothing from a fixture is ever put
beside a real record.

Nothing here logs or returns a value from a record. The rules turn it into statuses.
"""

import logging
import threading
from pathlib import Path
from typing import Protocol

from snapback.agent.intake import Listing
from snapback.agent.modules import ChallengeOutcome, FixtureModules
from snapback.agent.rules import check_price
from snapback.agent.rules.contact import check_authority
from snapback.agent.rules.owner import check_owner
from snapback.agent.scope import ListingScope
from snapback.contracts import (
    AuthorityResult,
    DataSource,
    FloorPlanCandidate,
    ForSaleMatch,
    LicenseResult,
    LocateResult,
    LocateStatus,
    OwnerResult,
    PhotoLocation,
    PriceResult,
    PropertyRecord,
    RuleHit,
    SpotCandidate,
    SpotRanking,
)

log = logging.getLogger("snapback.join")


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

    def license(self, listing_text: str) -> LicenseResult | None:
        """Does a poster who claims a real estate licence hold one? None means not looked up."""
        ...

    def owner(self, listing_text: str) -> OwnerResult | None:
        """Who owns the home in the listing, by the county roll? None means no owner data."""
        ...


def _ask(lookups: Lookups, name: str, listing_text: str):
    """One of lane D's later lookups (`license`, `owner`), or None when nothing was looked up.

    A lookup that broke is a lookup that did not happen: it must not stop the check, and it
    must not read as "looked up, nothing found". Lookups written before the method existed
    do not have it, and that is "not looked up" too. No value is logged.
    """
    lookup = getattr(lookups, name, None)
    if lookup is None or not listing_text:
        return None
    try:
        return lookup(listing_text)
    except Exception as error:
        log.warning("%s lookup failed (%s); treated as not looked up", name, type(error).__name__)
        return None


def license_of(lookups: Lookups, listing_text: str) -> LicenseResult | None:
    """Lane D's licence answer for this listing (D10), or None when nothing was looked up."""
    return _ask(lookups, "license", listing_text)


def owner_of(lookups: Lookups, listing_text: str) -> OwnerResult | None:
    """Lane D's owner of record for the home in this listing (D12), or None when there is none."""
    return _ask(lookups, "owner", listing_text)


class KitLookups:
    """Lane D's adapters. The kit is parsed once and kept for the life of the process."""

    def __init__(self, source: DataSource, kit_dir: Path | None = None) -> None:
        self.source = source
        self._kit_dir = kit_dir
        self._records: dict[str, PropertyRecord] | None = None
        self._lock = threading.Lock()

    def records(self) -> dict[str, PropertyRecord]:
        """Every record in the kit by our id, parsed once. For routes that need more than one."""
        from snapback.adapters import costar_jsonl

        with self._lock:
            if self._records is None:
                try:
                    self._records = costar_jsonl.load_records(self.source, self._kit_dir)
                except costar_jsonl.KitNotFoundError:
                    raise KitMissing from None
            return self._records

    def record(self, property_id: str) -> PropertyRecord | None:
        return self.records().get(property_id)

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        try:
            from snapback.adapters import costar_residential
        except ImportError:
            return None  # lane D's lookup (D7) is not here: nothing was looked up
        try:
            return costar_residential.for_sale_lookup(listing_text, self.source, self._kit_dir)
        except Exception as error:
            # A lookup that broke is a lookup that did not happen. It must not stop the
            # check, and it must not read as "looked up, nothing found". No value is logged.
            log.warning(
                "for-sale lookup failed (%s); treated as not looked up", type(error).__name__
            )
            return None

    def license(self, listing_text: str) -> LicenseResult | None:
        # The licence list is a public service outside this machine (D10, #128). A fixture
        # run, and so every test, never calls out: only a live run looks anyone up.
        if self.source is not DataSource.LIVE:
            return None
        try:
            from snapback.adapters import trec
        except ImportError:
            return None  # lane D's lookup (D10) is not here: nothing was looked up
        return trec.check_license(listing_text)

    def owner(self, listing_text: str) -> OwnerResult | None:
        # D12 (#130) plugs in here: the county owner roll, filtered to the kit's houses. Until
        # it lands there is no owner data, and the card says ownership was not checked.
        return None


class NoStandIn(RuntimeError):
    """Something asked for the twin or the challenge in a case that has no stand-in for them."""


class JoinedModules:
    """What the agent calls: the record parts from lane D, the rest from the stand-in.

    `stand_in` is None for a live case. Stand-ins are fixture data, so a live case has no
    twin and no challenge until lanes V and D land the real ones: its photos read "not
    checked", nobody is asked to prove presence, and it cannot come out VERIFIED.
    """

    def __init__(
        self,
        *,
        stand_in: FixtureModules | None,
        listing: Listing,
        record: PropertyRecord | None,
        for_sale: ForSaleMatch | None,
        salt: str,
        record_source: DataSource | None,
        license: LicenseResult | None = None,
        owner: OwnerResult | None = None,
    ) -> None:
        self._stand_in = stand_in
        self._listing = listing
        self._record = record
        self._for_sale = for_sale
        self._license = license
        self._owner = owner
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
        # The listing brokerage on record may market the home as the manager may (ruling,
        # Sat 01:20). Lane D's lookup carries those names once D7 (#95) is on main.
        offices = getattr(self._for_sale, "offices", None) or ()
        return check_authority(self._listing.contacts, self._record, self._salt, offices)

    def for_sale(self, case_id: str) -> ForSaleMatch | None:
        return self._for_sale

    def license(self, case_id: str) -> LicenseResult | None:
        return self._license

    def owner(self, case_id: str) -> OwnerResult | None:
        # Lane D says who owns the home. What the poster says about owning it is added here.
        return check_owner(self._listing.contacts, self._owner)

    def record_source(self, case_id: str) -> DataSource | None:
        """Where the record parts came from, or None if there are none."""
        if self._record is None and self._for_sale is None:
            return None
        return self._record_source

    # --- the twin and the challenge: stand-ins, and only in a fixture case -----------------

    def has_twin(self, case_id: str) -> bool:
        if self._stand_in is None:
            return False
        # A building whose record has no 3D model has no twin, whatever the stand-in holds.
        if self._record is not None and not self._record.model_ids:
            return False
        return self._stand_in.has_twin(case_id)

    def photo_count(self, case_id: str) -> int:
        if not self.has_twin(case_id):
            return self._listing.photos  # the photos the renter actually sent
        return self._stand_in.photo_count(case_id)  # type: ignore[union-attr]

    def floor_plans(self, case_id: str) -> list[FloorPlanCandidate]:
        if not self.has_twin(case_id):
            return []
        return self._stand_in.floor_plans(case_id)  # type: ignore[union-attr]

    def locate(self, case_id: str) -> LocateResult | None:
        if self.has_twin(case_id):
            return self._stand_in.locate(case_id)  # type: ignore[union-attr]
        # No twin to place photos in. Each photo sent is recorded as not checked, so the
        # card says there is no 3D scan to check against, not that no photos were sent.
        sent = self._listing.photos
        if not sent:
            return None
        # Naming the building's model says its scan exists and is not in our index, which
        # the card puts differently from "there is no scan". The id itself is never shown.
        models = self._record.model_ids if self._record else []
        return LocateResult(
            case_id=case_id,
            photos=[
                PhotoLocation(
                    photo_id=f"l{number}",
                    status=LocateStatus.NOT_INDEXED,
                    model_id=models[0] if models else None,
                )
                for number in range(1, sent + 1)
            ],
            claimed_property_id=self._record.property_id if self._record else None,
            thresholds_version="none",
        )

    def spot_ranking(self, case_id: str, model_id: str | None) -> SpotRanking | None:
        if not self.has_twin(case_id):
            return None
        return self._stand_in.spot_ranking(case_id, model_id)  # type: ignore[union-attr]

    def new_code(self, case_id: str) -> str:
        return self._need_stand_in().new_code(case_id)

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        return self._need_stand_in().challenge(case_id, spot, code, text, attempt)

    @property
    def sent_messages(self) -> list[str]:
        return self._stand_in.sent_messages if self._stand_in is not None else []

    def _need_stand_in(self) -> FixtureModules:
        if self._stand_in is None:
            raise NoStandIn("a live case has no stand-in challenge")
        return self._stand_in

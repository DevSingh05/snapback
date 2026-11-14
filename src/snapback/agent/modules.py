"""What the agent calls to get evidence, and a fixture-backed stand-in for all of it.

The real modules belong to other lanes: locate, recapture and memory to vision, the record,
the price inputs and the challenge to data. Until they land, `FixtureModules` serves the
shared fixtures in `fixtures/contracts/`, so the agent runs end to end today.
"""

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from snapback.agent.rules import check_price
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, Claims, check_authority
from snapback.agent.scope import ListingScope
from snapback.contracts import (
    AuthorityResult,
    ChallengeResult,
    DataSource,
    FloorPlanCandidate,
    ForSaleMatch,
    LicenseResult,
    LocateResult,
    MemoryResult,
    ModuleEvidence,
    PriceResult,
    PropertyRecord,
    RecaptureResult,
    RuleHit,
    SpotCandidate,
    SpotRanking,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "contracts"

# No 0/O, 1/I/L: the renter reads the code out and the poster writes it on paper.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))


@dataclass(frozen=True)
class ChallengeOutcome:
    """Everything one challenge attempt produced: the result and the checks on its replies."""

    challenge: ChallengeResult
    recapture: list[RecaptureResult] = field(default_factory=list)
    memory: list[MemoryResult] = field(default_factory=list)
    # A14: the message was handed over and the poster's reply has not come. The case waits
    # (HOLD, never a failure) until `CaseSession.reply` is given the checked reply.
    awaiting_reply: bool = False
    # A14: the reply came after the deadline and is not a copy of a listing photo, so it was
    # not counted. The session asks again once (decision 4, Sat 02:45).
    late: bool = False


class Modules(Protocol):
    def listing_scope(self, case_id: str) -> ListingScope:
        """What kind of listing this is, as read by code from its own link and wording."""
        ...

    def has_twin(self, case_id: str) -> bool: ...

    def photo_count(self, case_id: str) -> int: ...

    def floor_plans(self, case_id: str) -> list[FloorPlanCandidate]:
        """Floor plans on record, for when no photo was placed to rank them."""
        ...

    def locate(self, case_id: str) -> LocateResult | None: ...

    def rules(self, case_id: str) -> list[RuleHit]: ...

    def price(self, case_id: str) -> PriceResult | None: ...

    def authority(self, case_id: str) -> AuthorityResult | None: ...

    def for_sale(self, case_id: str) -> ForSaleMatch | None:
        """Is the home listed for sale, or just rented? None when it was not looked up."""
        ...

    def license(self, case_id: str) -> LicenseResult | None:
        """The poster's claimed real estate licence, looked up. None when it was not."""
        ...

    def record_source(self, case_id: str) -> DataSource | None:
        """Where price, authority and for_sale came from, if not from where the case did."""
        ...

    def spot_ranking(self, case_id: str, model_id: str | None) -> SpotRanking | None: ...

    def new_code(self, case_id: str) -> str: ...

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        """Send `text`, the message the renter approved, and judge the reply."""
        ...


class FixtureModules:
    """Serves one evidence fixture piece by piece. The options exist for tests and demos."""

    def __init__(
        self,
        evidence_file: str = "module_evidence_hold.json",
        *,
        fixtures_dir: Path = FIXTURES_DIR,
        has_twin: bool = True,
        listing_scope: ListingScope = ListingScope.RENTAL,
        rules: list[RuleHit] | None = None,
        listed_rent: int | None = None,
        contacts: Claims | None = None,
        unit: str | None = None,
        beds: int | None = None,
        record_file: str = "property_record.json",
        for_sale: ForSaleMatch | None = None,
        license: LicenseResult | None = None,
        recapture_override: list[dict] | None = None,
        recapture_clears_after: int | None = None,
        spots_available: int | None = None,
    ) -> None:
        self.evidence = ModuleEvidence.model_validate_json(
            (fixtures_dir / evidence_file).read_text()
        )
        self.record = PropertyRecord.model_validate_json((fixtures_dir / record_file).read_text())
        self.ranking = SpotRanking.model_validate_json(
            (fixtures_dir / "spot_ranking.json").read_text()
        )
        self._has_twin = has_twin
        self._listing_scope = ListingScope(listing_scope)
        # The renter's own text is not fixture data: when intake has read it, its rule hits
        # and its rent replace the fixture's.
        self._rules = rules
        self._listed_rent = listed_rent
        self._contacts = contacts
        self._unit = unit
        self._beds = beds
        self._for_sale = for_sale
        self._license = license
        self.sent_messages: list[str] = []  # every challenge text handed over for sending
        self._recapture_override = (
            None
            if recapture_override is None
            else [RecaptureResult.model_validate(item) for item in recapture_override]
        )
        self._recapture_clears_after = recapture_clears_after
        self._spots_available = spots_available

    def listing_scope(self, case_id: str) -> ListingScope:
        return self._listing_scope

    def has_twin(self, case_id: str) -> bool:
        return self._has_twin and bool(self.record.model_ids)

    def photo_count(self, case_id: str) -> int:
        return len(self.evidence.locate.photos) if self.evidence.locate else 0

    def floor_plans(self, case_id: str) -> list[FloorPlanCandidate]:
        return [
            FloorPlanCandidate(
                property_id=self.record.property_id,
                model_id=model_id,
                floor_plan=floor_plan,
                photos_located=0,
                total_inliers=0,
            )
            for model_id, floor_plan in zip(
                self.record.model_ids, self.record.floor_plans, strict=False
            )
        ]

    def locate(self, case_id: str) -> LocateResult | None:
        return self.evidence.locate

    def rules(self, case_id: str) -> list[RuleHit]:
        return list(self.evidence.rules if self._rules is None else self._rules)

    def price(self, case_id: str) -> PriceResult | None:
        if self._listed_rent is None and self._unit is None and self._beds is None:
            return self.evidence.price
        return check_price(self._listed_rent, self.record, beds=self._beds, unit=self._unit)

    def authority(self, case_id: str) -> AuthorityResult | None:
        # The listing's own claims are compared only when the record has something to compare
        # them with. The shared fixture record has none, so it keeps the fixture's answer.
        record = self.record
        comparable = record.manager_company or record.site_phone_hash or record.website_host
        if self._contacts is None or not comparable:
            return self.evidence.authority
        return check_authority(self._contacts, record, FIXTURE_PHONE_SALT)

    def for_sale(self, case_id: str) -> ForSaleMatch | None:
        return self._for_sale if self._for_sale is not None else self.evidence.for_sale

    def license(self, case_id: str) -> LicenseResult | None:
        return self._license if self._license is not None else self.evidence.license

    def record_source(self, case_id: str) -> DataSource | None:
        return None  # all of a fixture case is fixture

    def spot_ranking(self, case_id: str, model_id: str | None) -> SpotRanking | None:
        if self._spots_available is None:
            return self.ranking
        kept, drawable = [], 0
        for spot in self.ranking.spots:
            if spot.overlaps_listing_photo:
                kept.append(spot)
            elif drawable < self._spots_available:
                kept.append(spot)
                drawable += 1
        return self.ranking.model_copy(update={"spots": kept})

    def new_code(self, case_id: str) -> str:
        return self.evidence.challenge.code if self.evidence.challenge else new_code()

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        if self.evidence.challenge is None:
            raise LookupError("this fixture has no challenge result")
        self.sent_messages.append(text)
        recapture = list(self.evidence.recapture)
        still_flagged = (
            self._recapture_clears_after is None or attempt < self._recapture_clears_after
        )
        if self._recapture_override is not None and still_flagged:
            recapture = list(self._recapture_override)
        return ChallengeOutcome(
            challenge=self.evidence.challenge,
            recapture=recapture,
            memory=list(self.evidence.memory),
        )

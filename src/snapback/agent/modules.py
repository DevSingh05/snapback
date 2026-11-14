"""What the agent calls to get evidence, and a fixture-backed stand-in for all of it.

The real modules belong to other lanes: locate, recapture and memory to vision, the record,
the price inputs and the challenge to data. Until they land, `FixtureModules` serves the
shared fixtures in `fixtures/contracts/`, so the agent runs end to end today.
"""

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from snapback.agent.scope import ListingScope
from snapback.contracts import (
    AuthorityResult,
    ChallengeResult,
    FloorPlanCandidate,
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
        recapture_override: list[dict] | None = None,
        recapture_clears_after: int | None = None,
        spots_available: int | None = None,
    ) -> None:
        self.evidence = ModuleEvidence.model_validate_json(
            (fixtures_dir / evidence_file).read_text()
        )
        self.record = PropertyRecord.model_validate_json(
            (fixtures_dir / "property_record.json").read_text()
        )
        self.ranking = SpotRanking.model_validate_json(
            (fixtures_dir / "spot_ranking.json").read_text()
        )
        self._has_twin = has_twin
        self._listing_scope = ListingScope(listing_scope)
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
        return list(self.evidence.rules)

    def price(self, case_id: str) -> PriceResult | None:
        return self.evidence.price

    def authority(self, case_id: str) -> AuthorityResult | None:
        return self.evidence.authority

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

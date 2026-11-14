import pytest

from snapback.contracts import (
    AuthorityStatus,
    DataSource,
    Evidence,
    LocateStatus,
    PhotoLocation,
    PresenceStatus,
    VerdictState,
)
from snapback.verdict import decide


def photo(status: LocateStatus, photo_id: str = "p1") -> PhotoLocation:
    return PhotoLocation(photo_id=photo_id, status=status)


def evidence(**overrides) -> Evidence:
    base = {
        "case_id": "case-1",
        "source": DataSource.FIXTURE,
        "photos": [photo(LocateStatus.LOCATED_IN_CLAIMED)],
    }
    return Evidence(**(base | overrides))


def test_located_photos_alone_are_only_hold():
    # The trap this product exists for: real photos prove nothing about the poster.
    assert decide(evidence()).state is VerdictState.HOLD


def test_no_reply_yet_is_hold_not_failure():
    result = decide(evidence(presence=PresenceStatus.WAITING, authority=AuthorityStatus.MISMATCH))
    assert result.state is VerdictState.HOLD


def test_presence_without_authority_stays_hold():
    result = decide(evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.UNKNOWN))
    assert result.state is VerdictState.HOLD


def test_presence_with_record_mismatch_stays_hold():
    result = decide(evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MISMATCH))
    assert result.state is VerdictState.HOLD


def test_presence_and_authority_together_verify():
    result = decide(
        evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MATCHES_RECORD)
    )
    assert result.state is VerdictState.VERIFIED


def test_forged_reply_is_dont_pay_with_its_reason():
    result = decide(
        evidence(presence=PresenceStatus.FORGED, forgery_reason="Reply is listing photo 3.")
    )
    assert result.state is VerdictState.DONT_PAY
    assert result.reasons == ["Reply is listing photo 3."]


def test_photo_from_another_property_is_dont_pay():
    photos = [photo(LocateStatus.LOCATED_IN_CLAIMED), photo(LocateStatus.LOCATED_ELSEWHERE, "p2")]
    assert decide(evidence(photos=photos)).state is VerdictState.DONT_PAY


@pytest.mark.parametrize("flag", ["price_flag", "payment_flag"])
def test_record_mismatch_plus_a_red_flag_is_dont_pay(flag):
    result = decide(evidence(authority=AuthorityStatus.MISMATCH, **{flag: True}))
    assert result.state is VerdictState.DONT_PAY


def test_red_flag_without_a_mismatch_is_not_dont_pay():
    assert decide(evidence(price_flag=True, payment_flag=True)).state is VerdictState.HOLD


@pytest.mark.parametrize(
    "photos",
    [[], [photo(LocateStatus.NOT_INDEXED)], [photo(LocateStatus.NOT_LOCATED)]],
)
def test_nothing_located_in_the_claimed_property_is_unverified(photos):
    assert decide(evidence(photos=photos)).state is VerdictState.UNVERIFIED


def test_verdict_keeps_the_data_source_label():
    assert decide(evidence(source=DataSource.LIVE)).source is DataSource.LIVE


def test_no_verdict_ever_says_scam():
    cases = [
        evidence(),
        evidence(presence=PresenceStatus.FORGED),
        evidence(photos=[photo(LocateStatus.LOCATED_ELSEWHERE)]),
        evidence(authority=AuthorityStatus.MISMATCH, price_flag=True),
        evidence(photos=[]),
    ]
    for case in cases:
        assert all("scam" not in reason.lower() for reason in decide(case).reasons)

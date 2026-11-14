"""Evidence in, verdict out.

Pure and deterministic: no I/O, no network, no model calls. A language model may explain a
verdict in words, but it never sets one.

v0 encodes the rules from the project plan as written. The integrator lane owns this file and
extends it; every rule here has a test in tests/test_verdict.py.
"""

from snapback.contracts import (
    AuthorityStatus,
    Evidence,
    LocateStatus,
    PresenceStatus,
    Verdict,
    VerdictState,
)


def decide(evidence: Evidence) -> Verdict:
    """Turn the evidence for one case into a verdict with plain-language reasons.

    The order of the checks is the policy:
    1. Proof of a problem gives DONT_PAY (forged reply, photos from another property, or a
       record mismatch together with a price or payment red flag).
    2. No photo placed in the claimed property gives UNVERIFIED.
    3. Presence proven and authority matching the record gives VERIFIED.
    4. Everything else is HOLD, including "no reply yet" and "present but not on the record".
    """
    statuses = {photo.status for photo in evidence.photos}

    def verdict(state: VerdictState, *reasons: str) -> Verdict:
        return Verdict(
            case_id=evidence.case_id, state=state, reasons=list(reasons), source=evidence.source
        )

    if evidence.presence is PresenceStatus.FORGED:
        return verdict(
            VerdictState.DONT_PAY,
            evidence.forgery_reason
            or "The proof-of-presence reply was not a fresh photo taken in the unit.",
        )

    if LocateStatus.LOCATED_ELSEWHERE in statuses:
        return verdict(
            VerdictState.DONT_PAY, "At least one listing photo was taken in a different property."
        )

    red_flags = []
    if evidence.price_flag:
        red_flags.append("The rent is far below comparable units.")
    if evidence.payment_flag:
        red_flags.append("Payment was requested before any viewing.")
    if evidence.authority is AuthorityStatus.MISMATCH and red_flags:
        return verdict(
            VerdictState.DONT_PAY,
            "The poster does not match the contact on the property record.",
            *red_flags,
        )

    if LocateStatus.LOCATED_IN_CLAIMED not in statuses:
        if statuses <= {LocateStatus.NOT_INDEXED}:
            reason = (
                "This property has no 3D twin in our index, so the photos could not be checked."
            )
        else:
            reason = "The photos could not be located in this property's 3D twin."
        return verdict(VerdictState.UNVERIFIED, reason)

    if (
        evidence.presence is PresenceStatus.PROVEN
        and evidence.authority is AuthorityStatus.MATCHES_RECORD
    ):
        return verdict(
            VerdictState.VERIFIED,
            "The photos were located in this property.",
            "The poster matches the contact on the property record.",
            "A fresh photo proved someone was inside the unit.",
        )

    reasons = ["The photos were located in this property."]
    if evidence.authority is AuthorityStatus.MATCHES_RECORD:
        reasons.append("The poster matches the contact on the property record.")
    elif evidence.authority is AuthorityStatus.MISMATCH:
        reasons.append("The poster does not match the contact on the property record.")
    else:
        reasons.append("We could not confirm who is allowed to rent this unit.")
    if evidence.presence is PresenceStatus.PROVEN:
        reasons.append("A fresh photo proved someone was inside the unit, which is not authority.")
    else:
        reasons.append("Nobody has proved they are inside the unit yet.")
    return verdict(VerdictState.HOLD, *reasons)

"""Module evidence in, verdict and card out.

Deterministic and free of network or model calls. A language model may explain a verdict in
words, but it never sets a state and never writes a word that reaches a card: every string
comes from `snapback.card.strings`.

Three steps, each usable on its own:

1. `to_evidence` flattens what the modules produced (`ModuleEvidence`) into `Evidence`.
2. `decide` turns `Evidence` into a `Verdict`. It is the only place a state is chosen.
3. `build_card` lays the same facts out as the three-row card: PLACE, PERSON, PRICE.

Every rule here has a test in tests/test_verdict.py or tests/test_card_rows.py.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo

from snapback.card import strings
from snapback.contracts import (
    AuthorityStatus,
    Card,
    CardLine,
    CardRow,
    CardRowKind,
    CardTone,
    Evidence,
    ForSaleMatch,
    ForSaleStatus,
    LicenseStatus,
    LinkDomain,
    LocateStatus,
    MemoryHitKind,
    ModuleEvidence,
    PhoneMatch,
    PresenceStatus,
    PriceStatus,
    RuleCategory,
    UnitStatus,
    Verdict,
    VerdictState,
)

CARD_TTL = timedelta(hours=24)
FIXTURE_ID_PREFIX = "fx-"

# A red-flag rule in one of these categories is an ask for money or for details that let
# someone take money. Pressure and links are shown on the card but do not set the flag.
_PAYMENT_CATEGORIES = frozenset(
    {RuleCategory.PAYMENT_METHOD, RuleCategory.FEE_ASK, RuleCategory.DATA_ASK}
)

# Which label a fired rule sits under on the PRICE row.
_RULE_LABELS = {
    RuleCategory.PAYMENT_METHOD: "label.payment_ask",
    RuleCategory.FEE_ASK: "label.payment_ask",
    RuleCategory.LINK: "label.payment_ask",
    RuleCategory.DATA_ASK: "label.data_ask",
    RuleCategory.PRESSURE: "label.pressure",
}
_RULE_LABEL_ORDER = ("label.payment_ask", "label.data_ask", "label.pressure")

_UNIT_DOES_NOT_FIT = frozenset({UnitStatus.NOT_ON_RECORD, UnitStatus.BEDS_MISMATCH})


@dataclass(frozen=True)
class Presence:
    """What the challenge, the photo memory and the recapture check say together."""

    status: PresenceStatus
    copies_listing_photo: bool = False  # the reply is a copy of one of this case's photos
    copied_photo_number: int | None = None  # which one, counting from 1, when we can tell
    needs_new_photo: bool = False  # a recapture flag stopped a pass; ask again, accuse nobody


# Listing photos are named l1, l2, ... in the order the renter sent them.
_LISTING_PHOTO_ID = re.compile(r"l([1-9][0-9]{0,3})")


def _photo_number(modules: ModuleEvidence, photo_id: str | None) -> int | None:
    """Which listing photo this is, counting from 1.

    The id carries its own number. It is not looked up among the photos the twin placed:
    that list can be shorter than what the renter sent, and the number would be lost.
    """
    if photo_id is None:
        return None
    named = _LISTING_PHOTO_ID.fullmatch(photo_id)
    if named:
        return int(named.group(1))
    if modules.locate is None:
        return None
    for number, photo in enumerate(modules.locate.photos, start=1):
        if photo.photo_id == photo_id:
            return number
    return None


def presence_of(modules: ModuleEvidence) -> Presence:
    status = modules.challenge.presence if modules.challenge else PresenceStatus.NOT_REQUESTED

    copies = [hit for hit in modules.memory if hit.hit is MemoryHitKind.SAME_CASE_LISTING]
    if copies:
        return Presence(
            PresenceStatus.FORGED,
            copies_listing_photo=True,
            copied_photo_number=_photo_number(modules, copies[0].matched_listing_photo_id),
        )

    # A recapture flag can only stop a pass. It never turns into a forgery on its own.
    if status is PresenceStatus.PROVEN and any(result.blocks_pass for result in modules.recapture):
        return Presence(PresenceStatus.WAITING, needs_new_photo=True)

    return Presence(status)


def to_evidence(modules: ModuleEvidence, lang: str = strings.DEFAULT_LANG) -> Evidence:
    """Flatten the module outputs into the evidence `decide` reads. Missing modules are unknowns."""
    presence = presence_of(modules)

    forgery_reason = None
    if presence.copies_listing_photo:
        if presence.copied_photo_number is None:
            forgery_reason = strings.text("reason.forged_copy_unknown", lang)
        else:
            forgery_reason = strings.text(
                "reason.forged_copy", lang, n=presence.copied_photo_number
            )

    return Evidence(
        case_id=modules.case_id,
        source=modules.source,
        photos=list(modules.locate.photos) if modules.locate else [],
        authority=modules.authority.status if modules.authority else AuthorityStatus.UNKNOWN,
        presence=presence.status,
        forgery_reason=forgery_reason,
        price_flag=modules.price is not None and modules.price.status is PriceStatus.BELOW_RANGE,
        payment_flag=any(
            hit.red_flag and hit.category in _PAYMENT_CATEGORIES for hit in modules.rules
        ),
        rule_flag=any(hit.red_flag for hit in modules.rules),
        # For sale holds a case, unless the ad's phone is the office's on record: then the
        # brokerage itself is offering the home, and it is information (ruling, Sat 03:36).
        for_sale_flag=(
            _for_sale(modules) is ForSaleStatus.ACTIVE and not _the_ad_is_the_office_s(modules)
        ),
        recently_rented_flag=_for_sale(modules) is ForSaleStatus.RECENTLY_RENTED,
        phone_flag=(
            modules.authority is not None and modules.authority.office_phone_match is PhoneMatch.NO
        ),
        phone_confirmed=_the_ad_is_the_office_s(modules),
        lookalike_link_flag=(
            modules.authority is not None and modules.authority.link_domain is LinkDomain.LOOKALIKE
        ),
        unit_flag=modules.price is not None and modules.price.unit in _UNIT_DOES_NOT_FIT,
        license_flag=_license(modules) is LicenseStatus.NOT_FOUND,
    )


# The order reasons are given in (A21, #127). A renter asks two things first: "is this person
# allowed to rent it to me?" and "is this home even for rent?". Where the photos were taken
# and what the rent is come after. Every reason the verdict can give is listed here once; a
# test fails if a new one is added to the string table and not placed.
REASON_ORDER = (
    # Proof. It stands alone when there is any, so its place only matters for completeness.
    "reason.forged",
    "reason.forged_copy",
    "reason.forged_copy_unknown",
    "reason.photo_elsewhere",
    # Who: authority first, then the poster's contact, then the licence they claim.
    # (Owner of record goes here.)
    "reason.authority_matches",
    "reason.authority_unknown",
    "reason.phone_not_confirmed",
    "reason.phone_flag",
    "reason.lookalike_link",
    "reason.license_not_found",
    # Availability: is the home for rent at all?
    "reason.for_sale",
    # Presence: was someone inside, which is not the same as being allowed to rent it.
    "reason.presence_proven",
    "reason.presence_proven_not_authority",
    "reason.presence_missing",
    # Place.
    "reason.located",
    "reason.not_located",
    "reason.not_indexed",
    "reason.unit_flag",
    # Price, and what the renter's own text raised.
    "reason.price_flag",
    "reason.payment_flag",
    "reason.rule_flag",
)
_REASON_RANK = {key: rank for rank, key in enumerate(REASON_ORDER)}


def _for_sale(modules: ModuleEvidence) -> ForSaleStatus:
    return modules.for_sale.status if modules.for_sale else ForSaleStatus.NONE


def _license(modules: ModuleEvidence) -> LicenseStatus | None:
    """What the licence lookup (D10) found, or None when it never ran for this case."""
    return modules.license.status if modules.license else None


def _the_ad_is_the_office_s(modules: ModuleEvidence) -> bool:
    """The phone in the listing is the leasing office's on record."""
    authority = modules.authority
    return authority is not None and authority.office_phone_match is PhoneMatch.YES


def decide(evidence: Evidence, lang: str = strings.DEFAULT_LANG) -> Verdict:
    """Turn the evidence for one case into a verdict with plain-language reasons.

    The order of the checks is the policy:
    1. Only proof gives DONT_PAY: a forged reply, or a photo taken in another property. A record
       mismatch is not proof (owners live elsewhere, agents act for them), with or without a
       red flag beside it. A home listed for sale, a lookalike link, a phone that is not the
       leasing office's, a unit that does not fit the record and a licence number in the ad that is
       not active are not proof either.
    2. No photo placed in the claimed property gives UNVERIFIED, with what the record
       flagged listed among the reasons. One thing outranks it: a home listed for sale is
       HOLD, with that reason first, whether or not any photo could be placed.
    3. Presence proven, authority matching the record, the ad's phone being the leasing
       office's on record, and no red flag of any kind gives VERIFIED. The phone is needed
       (red team H1, Sat 03:25): anyone can type the manager's public name, and a door code
       or a former tenant gets a photo taken inside. A name match alone never verifies.
    4. Everything else is HOLD: no reply yet, present but not on the record, or any red flag
       (price, payment, fee, data ask, pressure, link, overpayment, for sale, lookalike
       link, unit, a licence number in the ad that is not active), or a phone that
       is not the leasing office's (not a red flag by itself, but not confirmed either).

    Two things hold nothing by themselves (ruling, Sat 01:20): a name that is not the one on
    record reads "not confirmed", and "recently rented" is information, since lease status
    is something we do not know.

    The reasons come out in `REASON_ORDER`: who and availability first, then presence, place
    and price. That is only the order they are read in; it changes no state.
    """
    statuses = {photo.status for photo in evidence.photos}

    def verdict(state: VerdictState, *keys: str, proof: str | None = None) -> Verdict:
        """The verdict, with its reasons in the order a renter asks about them."""
        if proof is not None:
            reasons = [proof]
        else:
            ordered = sorted(dict.fromkeys(keys), key=_REASON_RANK.__getitem__)
            reasons = [strings.text(key, lang) for key in ordered]
        return Verdict(
            case_id=evidence.case_id, state=state, reasons=reasons, source=evidence.source
        )

    # Proof is the whole reason for DONT_PAY. Nothing is put beside it.
    if evidence.presence is PresenceStatus.FORGED:
        forged = evidence.forgery_reason or strings.text("reason.forged", lang)
        return verdict(VerdictState.DONT_PAY, proof=forged)

    if LocateStatus.LOCATED_ELSEWHERE in statuses:
        return verdict(VerdictState.DONT_PAY, "reason.photo_elsewhere")

    # What the record and the licence list say against the listing. None of it is proof, so
    # none of it sets DONT_PAY, but it is said whatever the state turns out to be.
    on_record = [
        key
        for key, raised in (
            ("reason.for_sale", evidence.for_sale_flag),
            ("reason.lookalike_link", evidence.lookalike_link_flag),
            ("reason.unit_flag", evidence.unit_flag),
            # A18 (#124): the ad gives a licence number that is not an active Texas licence.
            ("reason.license_not_found", evidence.license_flag),
        )
        if raised
    ]
    # A phone that is not the leasing office's is not a red flag (ruling, Sat 02:10, #121):
    # a licensed locator or listing agent posting with their own number is normal. It still
    # holds a case, because the card cannot say "Checks passed" while the contact is
    # unconfirmed, and it is still said whatever the state turns out to be.
    # D10: a licence we could not confirm is no reason to call the number a red flag, so a
    # phone that is not the office's stays "not confirmed" whatever the licence list says.
    unconfirmed = ["reason.phone_flag"] if evidence.phone_flag else []

    if LocateStatus.LOCATED_IN_CLAIMED not in statuses:
        unplaced = (
            "reason.not_indexed" if statuses <= {LocateStatus.NOT_INDEXED} else "reason.not_located"
        )
        # For sale outranks "could not place" (conductor ruling, Sat 02:00). A home that is
        # for sale usually has no scan to place photos in, and "we could not check" is the
        # wrong thing to lead with. Still HOLD, never DONT_PAY: it is not proof.
        state = VerdictState.HOLD if evidence.for_sale_flag else VerdictState.UNVERIFIED
        return verdict(state, unplaced, *on_record, *unconfirmed)

    red_flags = []
    if evidence.price_flag:
        red_flags.append("reason.price_flag")
    if evidence.payment_flag:
        red_flags.append("reason.payment_flag")
    elif evidence.rule_flag:
        red_flags.append("reason.rule_flag")
    red_flags.extend(on_record)

    if (
        evidence.presence is PresenceStatus.PROVEN
        and evidence.authority is AuthorityStatus.MATCHES_RECORD
        and evidence.phone_confirmed
        and not red_flags
        and not unconfirmed
    ):
        return verdict(
            VerdictState.VERIFIED,
            "reason.located",
            "reason.authority_matches",
            "reason.presence_proven",
        )

    # A name that is not the one on record is not confirmed, and nothing worse: the manager,
    # the leasing office and a listing brokerage may all market a home.
    matches = evidence.authority is AuthorityStatus.MATCHES_RECORD
    proven = evidence.presence is PresenceStatus.PROVEN
    # H1: the name matches and the ad's contact was not shown to be the office. Said so the
    # hold has a reason. (A phone that is NOT the office's already has its own.)
    contact = []
    if matches and not evidence.phone_confirmed and not evidence.phone_flag:
        contact = ["reason.phone_not_confirmed"]
    return verdict(
        VerdictState.HOLD,
        "reason.located",
        "reason.authority_matches" if matches else "reason.authority_unknown",
        *contact,
        "reason.presence_proven_not_authority" if proven else "reason.presence_missing",
        *red_flags,
        *unconfirmed,
    )


# --- the card ----------------------------------------------------------------------------------


def _line(lang: str, label_key: str, tone: CardTone, text_key: str, **values: object) -> CardLine:
    return CardLine(
        label=strings.text(label_key, lang), text=strings.text(text_key, lang, **values), tone=tone
    )


def _floor_plan(modules: ModuleEvidence) -> str | None:
    if modules.locate is None or modules.locate.chosen is None:
        return None
    return modules.locate.chosen.floor_plan


def _seen_before_lines(modules: ModuleEvidence, lang: str, *, replies: bool) -> list[CardLine]:
    """One line per date a photo of ours turned up in another check. Never says which check."""
    reply_ids = set()
    if modules.challenge is not None:
        reply_ids = {spot.reply_photo_id for spot in modules.challenge.spots if spot.reply_photo_id}
    prefix = "here_now" if replies else "place"

    dates = set()
    for hit in modules.memory:
        if hit.hit is MemoryHitKind.OTHER_CHECK and (hit.photo_id in reply_ids) == replies:
            dates.add(hit.first_seen_on)

    lines = []
    for seen_on in sorted(dates, key=lambda day: (day is None, day)):
        if seen_on is None:
            lines.append(_line(lang, "label.seen_before", CardTone.HOLD, f"{prefix}.seen_before"))
        else:
            lines.append(
                _line(
                    lang,
                    "label.seen_before",
                    CardTone.HOLD,
                    f"{prefix}.seen_before_dated",
                    date=seen_on.isoformat(),
                )
            )
    return lines


def _place_row(modules: ModuleEvidence, lang: str) -> CardRow:
    photos = modules.locate.photos if modules.locate else []
    total = len(photos)
    located = sum(photo.status is LocateStatus.LOCATED_IN_CLAIMED for photo in photos)
    elsewhere = sum(photo.status is LocateStatus.LOCATED_ELSEWHERE for photo in photos)
    plan = _floor_plan(modules)

    if total == 0:
        main = _line(lang, "label.real", CardTone.NOT_CHECKED, "place.no_photos")
    elif elsewhere:
        main = _line(
            lang,
            "label.real",
            CardTone.RED_FLAG,
            "place.elsewhere",
            elsewhere=elsewhere,
            total=total,
        )
    elif located and plan:
        main = _line(
            lang,
            "label.real",
            CardTone.OK,
            "place.located_plan",
            floor_plan=plan,
            located=located,
            total=total,
        )
    elif located:
        main = _line(lang, "label.real", CardTone.OK, "place.located", located=located, total=total)
    elif all(photo.status is LocateStatus.NOT_INDEXED for photo in photos):
        # A photo that names a model belongs to a building whose scan exists and is not in
        # our index. With no model named, there is no scan of the building at all.
        has_scan = any(photo.model_id for photo in photos)
        key = "place.not_indexed_yet" if has_scan else "place.not_indexed"
        main = _line(lang, "label.real", CardTone.NOT_CHECKED, key)
    else:
        main = _line(lang, "label.real", CardTone.NOT_SHOWN, "place.not_located")

    return CardRow(
        kind=CardRowKind.PLACE,
        lines=[
            main,
            *_from_record(modules, [*_for_sale_lines(modules, lang), *_unit_lines(modules, lang)]),
            *_seen_before_lines(modules, lang, replies=False),
        ],
    )


def _from_record(modules: ModuleEvidence, lines: list[CardLine]) -> list[CardLine]:
    """Mark lines that came from the record, when the record is not from where the case is.

    A case can hold a real record beside stand-ins for the twin and the challenge. The card
    as a whole then stays FIXTURE, and these lines say for themselves that they are LIVE.
    """
    source = modules.record_source
    if source is None or source is modules.source:
        return lines
    return [line.model_copy(update={"source": source}) for line in lines]


MAX_BROKERAGE_CHARS = 80


def _for_sale_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    status = _for_sale(modules)
    if status is ForSaleStatus.ACTIVE:
        # A warning, not a red flag, and never "not for rent" (red team H5, Sat 03:25): homes
        # for sale are sometimes also offered for lease, and whether this one is leased is
        # something we do not know. The line says what the record says and who to ask.
        found = modules.for_sale
        offices = [" ".join(name.split())[:MAX_BROKERAGE_CHARS] for name in found.offices]
        brokerage = next((name for name in offices if name), None)
        since = found.listed_on.isoformat() if found.listed_on else None
        record_key = {
            (True, True): "place.for_sale_record",
            (True, False): "place.for_sale_record_no_date",
            (False, True): "place.for_sale_record_no_brokerage",
            (False, False): "place.for_sale_record_bare",
        }[(brokerage is not None, since is not None)]
        record = strings.text(
            record_key, lang, site=found.site, brokerage=brokerage or "", date=since or ""
        )
        if _the_ad_is_the_office_s(modules):
            # The brokerage itself is offering the home (ruling, Sat 03:36). Information
            # only: it holds nothing, and the renter is told who to ask.
            key = "place.for_sale_office"
            return [_line(lang, "label.for_sale", CardTone.NOT_SHOWN, key, record=record)]
        key = "place.for_sale" if brokerage is not None else "place.for_sale_ask_listing"
        return [_line(lang, "label.for_sale", CardTone.HOLD, key, record=record)]
    if status is ForSaleStatus.RECENTLY_RENTED:
        rented_on = modules.for_sale.changed_on if modules.for_sale else None
        # Information, not a flag: we do not know whether it is rented now.
        if rented_on is not None:
            return [
                _line(
                    lang,
                    "label.recently_rented",
                    CardTone.NOT_SHOWN,
                    "place.recently_rented_dated",
                    date=rented_on.isoformat(),
                )
            ]
        return [_line(lang, "label.recently_rented", CardTone.NOT_SHOWN, "place.recently_rented")]
    return []


def _aware(moment: datetime, what: str) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{what} must carry a timezone, got a naive datetime: {moment!r}")
    return moment


def _here_now_line(modules: ModuleEvidence, lang: str, zone: tzinfo) -> CardLine:
    presence = presence_of(modules)
    label = "label.here_now"

    if presence.status is PresenceStatus.FORGED:
        if not presence.copies_listing_photo:
            return _line(lang, label, CardTone.RED_FLAG, "here_now.forged")
        if presence.copied_photo_number is None:
            return _line(lang, label, CardTone.RED_FLAG, "here_now.forged_copy_unknown")
        return _line(
            lang, label, CardTone.RED_FLAG, "here_now.forged_copy", n=presence.copied_photo_number
        )

    if presence.needs_new_photo:
        # With no retry left, do not tell the renter to ask for a photo nobody will check.
        key = "here_now.no_retry_left" if modules.no_retry_left else "here_now.retry"
        return _line(lang, label, CardTone.HOLD, key)

    if presence.status is PresenceStatus.WAITING:
        # A reply may have come and settled nothing (A14). Say what it showed.
        answered = [
            spot
            for spot in (modules.challenge.spots if modules.challenge else [])
            if spot.replied_at is not None
        ]
        if answered and answered[-1].code_read and answered[-1].located is None:
            return _line(lang, label, CardTone.NOT_SHOWN, "here_now.code_only")
        if modules.no_retry_left:
            return _line(lang, label, CardTone.HOLD, "here_now.no_retry_left")
        if answered and answered[-1].code_read is False:
            return _line(lang, label, CardTone.HOLD, "here_now.code_missing")
        return _line(lang, label, CardTone.HOLD, "here_now.waiting")

    if presence.status is PresenceStatus.NOT_REQUESTED:
        return _line(lang, label, CardTone.NOT_CHECKED, "here_now.not_requested")

    # Replies can arrive stamped in different zones. Compare them as instants, then show the
    # latest one on the card's own clock.
    spots = modules.challenge.spots if modules.challenge else []
    replied = [spot.replied_at.astimezone(zone) for spot in spots if spot.replied_at is not None]
    if not replied:
        return _line(lang, label, CardTone.OK, "here_now.proven_bare")
    details = {
        "matched": sum(bool(spot.located and spot.code_read) for spot in spots),
        "total": len(spots),
        "time": max(replied).strftime("%H:%M"),
    }
    plan = _floor_plan(modules)
    if plan:
        return _line(lang, label, CardTone.OK, "here_now.proven_plan", floor_plan=plan, **details)
    return _line(lang, label, CardTone.OK, "here_now.proven", **details)


def _allowed_line(modules: ModuleEvidence, lang: str) -> CardLine:
    # The card says yes or no about the record. It never repeats what the poster called
    # themselves, which may be a person's name.
    status = modules.authority.status if modules.authority else AuthorityStatus.UNKNOWN
    if status is AuthorityStatus.MATCHES_RECORD:
        # A match does not lift this line: anyone can type a company's public name. The card
        # names the manager on record (a company, never a person) so the renter can call them.
        manager = modules.authority.manager_on_record if modules.authority else None
        if manager:
            return _line(
                lang, "label.allowed", CardTone.NOT_SHOWN, "allowed.call_manager", manager=manager
            )
        return _line(lang, "label.allowed", CardTone.NOT_SHOWN, "allowed.call_manager_unnamed")
    if status is AuthorityStatus.MISMATCH:
        # Not a red flag: the name they gave may be a brokerage or an office we do not hold.
        return _line(lang, "label.allowed", CardTone.NOT_SHOWN, "allowed.call_office")
    return _line(lang, "label.allowed", CardTone.NOT_SHOWN, "allowed.not_shown")


def _contact_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """The phone yes/no and a lookalike link. Never the number, never the record's address."""
    authority = modules.authority
    if authority is None:
        return []
    lines = []
    if authority.office_phone_match is PhoneMatch.YES:
        # Supporting only: the number is public, so this is not who the poster is.
        lines.append(_line(lang, "label.contact", CardTone.OK, "contact.phone_match"))
    elif authority.office_phone_match is PhoneMatch.NO:
        # Not confirmed, never a red flag by itself (ruling, Sat 02:10, #121): agents and
        # locators often post with their own number.
        if authority.manager_on_record:
            lines.append(
                _line(
                    lang,
                    "label.contact",
                    CardTone.NOT_SHOWN,
                    "contact.phone_mismatch",
                    manager=authority.manager_on_record,
                )
            )
        else:
            lines.append(
                _line(lang, "label.contact", CardTone.NOT_SHOWN, "contact.phone_mismatch_unnamed")
            )
    elif authority.status is AuthorityStatus.MATCHES_RECORD:
        # H1: the name matches and there was no phone to compare. "Checks passed" needs the
        # ad's contact to be the office's, so the card says this was not checked.
        lines.append(_line(lang, "label.contact", CardTone.NOT_CHECKED, "contact.phone_unchecked"))
    if authority.link_domain is LinkDomain.LOOKALIKE:
        lines.append(_line(lang, "label.link", CardTone.RED_FLAG, "contact.lookalike_link"))
    return lines


MAX_SPONSOR_CHARS = 80


def _license_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """The licence the poster claims, as the Texas list answers it (A18, #124; lookup: D10).

    Never a person's name, never a licence number, never the poster's own words. A licence
    found is a supporting line: it does not answer "allowed to rent it", so it never lifts
    that line and never verifies a case. NOT_FOUND happens only for a licence number the ad
    itself gives (D10): a red flag (the ad's number contradicts the ad) that holds the
    case. It is not proof, so it never gives DONT_PAY.
    A claim we could not check says to ask for the number and look it up.
    A lookup that did not happen, or an ad with no claim, says nothing.
    """
    found = modules.license
    if found is None:
        return []  # never looked up for this case: no line, as with any module that is absent
    label = "label.license"
    if found.status is LicenseStatus.NOT_FOUND:
        return [_line(lang, label, CardTone.RED_FLAG, "license.not_found")]
    if found.status is LicenseStatus.LICENSED:
        sponsor = " ".join((found.sponsor_broker or "").split())[:MAX_SPONSOR_CHARS]
        if sponsor:
            return [_line(lang, label, CardTone.OK, "license.licensed_sponsored", broker=sponsor)]
        return [_line(lang, label, CardTone.OK, "license.licensed")]
    if found.claimed_role:
        return [_line(lang, label, CardTone.NOT_CHECKED, "license.not_checked_claimed")]
    return []  # no claim, so nothing to say


def _person_row(modules: ModuleEvidence, lang: str, zone: tzinfo) -> CardRow:
    return CardRow(
        kind=CardRowKind.PERSON,
        lines=[
            _here_now_line(modules, lang, zone),
            *_from_record(modules, [_allowed_line(modules, lang), *_contact_lines(modules, lang)]),
            # Not from the record: the licence list is the state's, and public.
            *_license_lines(modules, lang),
            *_seen_before_lines(modules, lang, replies=True),
        ],
    )


def _rule_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """Red-flag rules, grouped under their labels. "Payment ask" is always there, and first."""
    by_label: dict[str, list[CardLine]] = {label: [] for label in _RULE_LABEL_ORDER}
    shown = set()
    for hit in modules.rules:
        if not hit.red_flag or hit.rule_id in shown:
            continue
        shown.add(hit.rule_id)
        key = f"rule.{hit.rule_id}"
        if not strings.has(key, lang):
            key = f"rule_category.{hit.category.value}"
        label = _RULE_LABELS[hit.category]
        by_label[label].append(_line(lang, label, CardTone.RED_FLAG, key))
    if not by_label["label.payment_ask"]:
        by_label["label.payment_ask"].append(
            _line(lang, "label.payment_ask", CardTone.OK, "payment.none")
        )
    return [line for label in _RULE_LABEL_ORDER for line in by_label[label]]


def _rent_line(modules: ModuleEvidence, lang: str) -> CardLine:
    # Only how the asked rent compares. The record's own figures are sponsor data and stay off
    # the card.
    status = modules.price.status if modules.price else PriceStatus.NOT_CHECKED
    if modules.price is not None and modules.price.per_bed:
        return _line(lang, "label.rent_vs_record", CardTone.NOT_CHECKED, "rent.per_bed")
    if status is PriceStatus.WITHIN_RANGE:
        return _line(lang, "label.rent_vs_record", CardTone.OK, "rent.within_range")
    if status is PriceStatus.BELOW_RANGE:
        price = modules.price
        if price and price.compared_beds is not None and price.record_min and price.listed_rent:
            # Against floor plans of the listing's own size, say how far under. The percent is
            # ours; the record's rents themselves stay off the card.
            beds = price.compared_beds
            plan = strings.text("rent.plan.beds", lang, beds=beds)
            if beds == 0:
                plan = strings.text("rent.plan.studio", lang)
            percent = round(100 * (price.record_min - price.listed_rent) / price.record_min)
            return _line(
                lang,
                "label.rent_vs_record",
                CardTone.HOLD,
                "rent.below_floor_plan",
                percent=percent,
                plan=plan,
            )
        return _line(lang, "label.rent_vs_record", CardTone.HOLD, "rent.below_range")
    return _line(lang, "label.rent_vs_record", CardTone.NOT_CHECKED, "rent.not_checked")


def _rent_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    line = _rent_line(modules, lang)
    price = modules.price
    # A rent line that compared nothing says nothing about the record.
    compared = price is not None and (price.status is not PriceStatus.NOT_CHECKED or price.per_bed)
    return _from_record(modules, [line]) if compared else [line]


def _unit_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    # The line never repeats the unit number: it is the renter's own text, and the card is
    # passed around.
    unit = modules.price.unit if modules.price else UnitStatus.NOT_CHECKED
    if unit is UnitStatus.NOT_ON_RECORD:
        return [_line(lang, "label.unit", CardTone.HOLD, "unit.not_on_record")]
    if unit is UnitStatus.BEDS_MISMATCH:
        return [_line(lang, "label.unit", CardTone.HOLD, "unit.beds_mismatch")]
    return []


def _price_row(modules: ModuleEvidence, lang: str) -> CardRow:
    return CardRow(
        kind=CardRowKind.PRICE,
        lines=[*_rule_lines(modules, lang), *_rent_lines(modules, lang)],
    )


def build_card(
    modules: ModuleEvidence,
    *,
    checked_at: datetime | None = None,
    verify_base_url: str | None = None,
    lang: str = strings.DEFAULT_LANG,
) -> Card:
    """Lay one case out as the three-row card. The state comes from `decide`, nowhere else.

    `checked_at` defaults to now (UTC); pass it to get a reproducible card. Its timezone is the
    card's clock: every time printed on the card is shown in it. `verify_base_url` is the web
    app's address; without it the card carries no verify link.

    Raises ValueError if `checked_at` or any reply time has no timezone.
    """
    verdict = decide(to_evidence(modules, lang), lang)
    public_id = modules.case_id.removeprefix(FIXTURE_ID_PREFIX)
    checked = _aware(checked_at, "checked_at") if checked_at is not None else datetime.now(UTC)
    for spot in modules.challenge.spots if modules.challenge else []:
        if spot.replied_at is not None:
            _aware(spot.replied_at, f"replied_at of spot {spot.spot_id}")

    verify_url = None
    if verify_base_url:
        verify_url = f"{verify_base_url.rstrip('/')}/c/{public_id}"

    return Card(
        case_id=public_id,
        source=modules.source,
        state=verdict.state,
        checked_at=checked,
        expires_at=checked + CARD_TTL,
        rows=[
            _place_row(modules, lang),
            _person_row(modules, lang, checked.tzinfo),
            _price_row(modules, lang),
        ],
        not_checked=[
            strings.text("not_checked.id", lang),
            strings.text("not_checked.lease", lang),
            strings.text("not_checked.ownership", lang),
        ],
        footer=[
            strings.text("footer.two_rules", lang),
            strings.text("footer.only_trust", lang),
        ],
        verify_url=verify_url,
        lang=lang,
        for_sale=_for_sale_finding(modules),
    )


def _for_sale_finding(modules: ModuleEvidence) -> ForSaleMatch | None:
    """The for-sale lookup, when it found something. "Looked up, nothing" is not a finding."""
    found = modules.for_sale
    if found is None or found.status is ForSaleStatus.NONE:
        return None
    return found

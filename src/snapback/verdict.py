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
    AerialStatus,
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
    OwnerKind,
    OwnerMatch,
    PhoneMatch,
    PresenceStatus,
    PriceStatus,
    PublishedRule,
    RuleCategory,
    UnitStatus,
    Verdict,
    VerdictState,
)
from snapback.settings import get_settings

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
_BOTH_MONEY_RULES = frozenset(
    {"payment.zelle_before_viewing", "fee.holding_deposit_before_viewing"}
)

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
        # A phone that is not the office's holds the case, unless an active licence checked by
        # number is sponsored by the brokerage on record (Vidyut, Sat 07:35): that clears this
        # one reason only. phone_confirmed stays False, so it can never verify a case.
        phone_flag=(
            modules.authority is not None
            and modules.authority.office_phone_match is PhoneMatch.NO
            and _licence_clears_contact(modules) is None
        ),
        phone_cleared_by_licence=(
            modules.authority is not None
            and modules.authority.office_phone_match is PhoneMatch.NO
            and _licence_clears_contact(modules) is not None
        ),
        phone_confirmed=_the_ad_is_the_office_s(modules),
        brokerage_only=modules.authority is not None and modules.authority.brokerage_only,
        lookalike_link_flag=(
            modules.authority is not None and modules.authority.link_domain is LinkDomain.LOOKALIKE
        ),
        unit_flag=modules.price is not None and modules.price.unit in _UNIT_DOES_NOT_FIT,
        aerial_wrong_building_flag=(
            get_settings().snapback_vexcel_in_verdict
            and modules.aerial is not None
            and modules.aerial.status is AerialStatus.WRONG_BUILDING
        ),
        license_flag=_license(modules) is LicenseStatus.NOT_FOUND and not _renter_number(modules),
        license_given_flag=(
            _license(modules) is LicenseStatus.NOT_FOUND and _renter_number(modules)
        ),
        owner_flag=_owner_is_not_the_poster(modules),
        office_confirmed_domain=modules.office_confirmed_domain,
        office_declined_domain=modules.office_declined_domain,
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
    # Who: authority first, then the poster's contact, the licence they claim, and the
    # owner of record.
    "reason.authority_matches",
    "reason.authority_matches_brokerage",
    "reason.office_confirmed",
    "reason.office_declined",
    "reason.authority_unknown",
    "reason.phone_not_confirmed",
    "reason.phone_not_confirmed_brokerage",
    "reason.phone_flag",
    "reason.lookalike_link",
    "reason.license_not_found",
    "reason.license_not_found_given",
    "reason.owner_not_poster",
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
    "reason.aerial_wrong_building",
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


def _renter_number(modules: ModuleEvidence) -> bool:
    """The licence number that was looked up is the one the renter typed (A24 stretch)."""
    return modules.license is not None and modules.license.number_from == "renter"


def _owner_is_not_the_poster(modules: ModuleEvidence) -> bool:
    """The poster says they own the home, and the owner of record is someone else (A19).

    A company the poster does not name, or a person whose name is not the one they gave.
    "Not checked" is never this: a near-miss spelling or no name to compare holds nothing.
    """
    owner = modules.owner
    return owner is not None and owner.poster_says_owner and owner.poster_matches is OwnerMatch.NO


def _the_ad_is_the_office_s(modules: ModuleEvidence) -> bool:
    """The phone in the listing is the leasing office's on record."""
    authority = modules.authority
    return authority is not None and authority.office_phone_match is PhoneMatch.YES


def _licence_clears_contact(modules: ModuleEvidence) -> str | None:
    """The brokerage on record, when an active licence clears the contact line (Vidyut, Sat 07:35).

    All five must hold: presence is PROVEN (a fresh in-home photo with the code, Vidyut Sat
    09:05: a copied licence is defeated only by that); the licence is active (LICENSED); it
    was checked by NUMBER (the ad's or the renter's, never a name lookup); its sponsor is a
    company; and that company is the brokerage or office on record (the authority's, or a
    listing office of an ACTIVE for-sale match), by the same matcher as everywhere else. Then
    a phone that is not the office's is information, not "Not confirmed". It verifies
    nothing, even with presence (a door code or a copied name and number can pass all of it,
    Vidyut Sat 09:30); the owner line and the for-sale hold are
    not touched.
    Returns that brokerage's name from the record, or None.
    """
    # Imported here: snapback.agent imports this module while it loads.
    from snapback.agent.rules.contact import same_company

    found = modules.license
    if (
        found is None
        # Presence PROVEN is needed too (Vidyut, Sat 09:05): a real agent's name and number are
        # public, so only a fresh in-home photo with the code separates them from a copier.
        or presence_of(modules).status is not PresenceStatus.PROVEN
        or found.status is not LicenseStatus.LICENSED
        or found.number_from not in ("ad", "renter")
        or not found.sponsor_broker
    ):
        return None
    on_record = []
    if modules.authority is not None and modules.authority.manager_on_record:
        on_record.append(modules.authority.manager_on_record)
    if modules.for_sale is not None and modules.for_sale.status is ForSaleStatus.ACTIVE:
        on_record.extend(modules.for_sale.offices)
    return next(
        (name for name in on_record if same_company(found.sponsor_broker, name) is True), None
    )


def decide(evidence: Evidence, lang: str = strings.DEFAULT_LANG) -> Verdict:
    """Turn the evidence for one case into a verdict with plain-language reasons.

    The order of the checks is the policy:
    1. Only proof gives DONT_PAY: a forged reply, or a photo taken in another property. A record
       mismatch is not proof (owners live elsewhere, agents act for them), with or without a
       red flag beside it. A home listed for sale, a lookalike link, a phone that is not the
       leasing office's, a unit that does not fit the record and a licence number in the ad that is
       not active are not proof either.
    2. No photo placed in the claimed property (none sent, or none placed) gives UNVERIFIED,
       with what the record flagged listed among the reasons. Any red flag outranks it (#10):
       price, payment, fee, data ask, pressure, link, overpayment, for sale, lookalike link,
       unit or a licence number in the ad that is not active gives HOLD, the verdict the same
       flags give with photos, whether or not any photo could be placed. Something only "not
       confirmed" (step 4) does not outrank it.
    3. Presence proven, authority matching the record, the ad's phone being the leasing
       office's on record, and no red flag of any kind gives VERIFIED. The phone is needed
       (red team H1, Sat 03:25): anyone can type the manager's public name, and a door code
       or a former tenant gets a photo taken inside. A name match alone never verifies.
    4. Everything else is HOLD: no reply yet, present but not on the record, or any red flag
       (price, payment, fee, data ask, pressure, link, overpayment, for sale, lookalike
       link, unit, a licence number in the ad that is not active), or something not
       confirmed that is not a red flag by itself: a phone that is not the leasing
       office's, or a poster who says they own a home whose owner of record is someone else.

    Two things hold nothing by themselves (ruling, Sat 01:20): a name that is not the one on
    record reads "not confirmed", and "recently rented" is information, since lease status
    is something we do not know.

    The reasons come out in `REASON_ORDER`: who and availability first, then presence, place
    and price. That is only the order they are read in; it changes no state.
    """
    statuses = {photo.status for photo in evidence.photos}

    def verdict(
        state: VerdictState, *keys: str, proof: str | None = None, **values: str
    ) -> Verdict:
        """The verdict, with its reasons in the order a renter asks about them."""
        if proof is not None:
            reasons = [proof]
        else:
            ordered = sorted(dict.fromkeys(keys), key=_REASON_RANK.__getitem__)
            # {domain} is only in the office reasons; the declined one is the default.
            fill = {"domain": evidence.office_declined_domain or "", **values}
            reasons = [strings.text(key, lang, **fill) for key in ordered]
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
            # Behind SNAPBACK_VEXCEL_IN_VERDICT: holds, is not proof, never clears.
            ("reason.aerial_wrong_building", evidence.aerial_wrong_building_flag),
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
    if evidence.phone_cleared_by_licence:
        # The licence is a number anyone can copy from a real listing (review H1): the contact
        # is still not shown to be the office, so a contact reason always remains.
        unconfirmed = ["reason.phone_not_confirmed"]
    if evidence.license_given_flag:
        # A24 stretch (ruling, Sat 07:14): a number the renter typed may be a typo. Not
        # confirmed and HOLD, never a red flag, and never in a report pack.
        unconfirmed = [*unconfirmed, "reason.license_not_found_given"]
    if evidence.office_declined_domain:
        # The office at the website on record said this ad is not theirs. Not confirmed, and
        # it holds the case; it is an answer, not proof, so never a red flag.
        unconfirmed = [*unconfirmed, "reason.office_declined"]
    if evidence.owner_flag:
        # A19 (#125): the poster says they own it and the owner of record is someone else.
        # Not confirmed, like any name that does not match (ruling, Sat 01:20): owners rent
        # through family, trusts and companies. It holds the case and is never a red flag.
        unconfirmed = [*unconfirmed, "reason.owner_not_poster"]

    red_flags = []
    if evidence.price_flag:
        red_flags.append("reason.price_flag")
    if evidence.payment_flag:
        red_flags.append("reason.payment_flag")
    elif evidence.rule_flag:
        red_flags.append("reason.rule_flag")
    red_flags.extend(on_record)

    if LocateStatus.LOCATED_IN_CLAIMED not in statuses:
        unplaced = (
            "reason.not_indexed" if statuses <= {LocateStatus.NOT_INDEXED} else "reason.not_located"
        )
        # A red flag outranks "could not place" (conductor ruling, Sat 02:00, for sale; issue
        # #10, every red flag): no photos, or none placed, does not soften a lookalike link, a
        # payment by app or a fee before a viewing. The verdict is the one the same flags give
        # with photos, HOLD, never DONT_PAY: none of it is proof. "Not confirmed" alone is not
        # a red flag and still reads UNVERIFIED here.
        state = VerdictState.HOLD if red_flags else VerdictState.UNVERIFIED
        return verdict(state, unplaced, *red_flags, *unconfirmed)

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

    # Vidyut, Sat 09:38: someone at the office's own website domain on CoStar's record opened
    # a one-time link for this case. That stands in for the phone match, and only here: the
    # photos are placed in the claimed home (above), presence is proven, the name matches the
    # record, and nothing else holds the case (no red flag, no phone that is not the office's,
    # no unconfirmed owner or licence). The field is set only by snapback.office from the
    # record's website, so a domain from the ad cannot get here. Presence alone and a licence
    # alone still never verify.
    if (
        evidence.office_confirmed_domain
        and evidence.presence is PresenceStatus.PROVEN
        and evidence.authority is AuthorityStatus.MATCHES_RECORD
        and not red_flags
        and not unconfirmed
    ):
        return verdict(
            VerdictState.VERIFIED,
            "reason.located",
            "reason.authority_matches",
            "reason.office_confirmed",
            "reason.presence_proven",
            domain=evidence.office_confirmed_domain or "",
        )

    # A name that is not the one on record is not confirmed, and nothing worse: the manager,
    # the leasing office and a listing brokerage may all market a home.
    matches = evidence.authority is AuthorityStatus.MATCHES_RECORD
    proven = evidence.presence is PresenceStatus.PROVEN
    # A15: on a home for sale with no property record, who is on record is a listing
    # brokerage. The reasons then say "brokerage", never "manager" or "leasing office".
    by_brokerage = "_brokerage" if evidence.brokerage_only else ""
    # H1: the name matches and the ad's contact was not shown to be the office. Said so the
    # hold has a reason. (A phone that is NOT the office's already has its own.)
    contact = []
    if (
        matches
        and not evidence.phone_confirmed
        and not evidence.phone_flag
        and not evidence.phone_cleared_by_licence
    ):
        contact = [f"reason.phone_not_confirmed{by_brokerage}"]
    return verdict(
        VerdictState.HOLD,
        "reason.located",
        f"reason.authority_matches{by_brokerage}" if matches else "reason.authority_unknown",
        *contact,
        "reason.presence_proven_not_authority" if proven else "reason.presence_missing",
        *red_flags,
        *unconfirmed,
    )


# --- the card ----------------------------------------------------------------------------------


def _line(lang: str, label_key: str, tone: CardTone, text_key: str, **values: object) -> CardLine:
    return CardLine(
        label=strings.text(label_key, lang),
        text=strings.text(text_key, lang, **values),
        tone=tone,
        key=label_key,
    )


# What a record calls a house: the kit's residential adapter says "house", and the staged
# cases say "single family".
_HOUSE_KINDS = frozenset({"house", "single family"})


def _is_a_house(modules: ModuleEvidence) -> bool:
    kind = (modules.property_type or "").lower().replace("_", " ").replace("-", " ")
    return " ".join(kind.split()) in _HOUSE_KINDS


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
        key = "place.located_home" if _is_a_house(modules) else "place.located"
        main = _line(lang, "label.real", CardTone.OK, key, located=located, total=total)
    elif all(photo.status is LocateStatus.NOT_INDEXED for photo in photos):
        # A photo that names a model belongs to a building whose scan exists and is not in
        # our index. With no model named, there is no scan of the building at all.
        has_scan = any(photo.model_id for photo in photos)
        key = "place.not_indexed_yet" if has_scan else "place.not_indexed"
        main = _line(lang, "label.real", CardTone.NOT_CHECKED, key)
    else:
        main = _line(lang, "label.real", CardTone.NOT_SHOWN, "place.not_located")

    matched = []
    if elsewhere and modules.matched_office:
        matched = [
            _line(
                lang,
                "label.matched_home",
                CardTone.NOT_CHECKED,
                "place.matched_office",
                office=modules.matched_office,
            )
        ]
    return CardRow(
        kind=CardRowKind.PLACE,
        lines=[
            main,
            *_from_record(modules, matched),
            *_from_record(modules, [*_for_sale_lines(modules, lang), *_unit_lines(modules, lang)]),
            *_record_lines(modules, lang, place=True),
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


def for_sale_record(found: ForSaleMatch, lang: str) -> tuple[str, str | None]:
    """What the for-sale record says, in the card's LOCKED words, and the brokerage it names.
    One place builds this sentence, so a search line and the card never word it differently."""
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
    return record, brokerage


def _for_sale_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    status = _for_sale(modules)
    if status is ForSaleStatus.ACTIVE:
        # A warning, not a red flag, and never "not for rent" (red team H5, Sat 03:25): homes
        # for sale are sometimes also offered for lease, and whether this one is leased is
        # something we do not know. The line says what the record says and who to ask.
        found = modules.for_sale
        record, brokerage = for_sale_record(found, lang)
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
        cleared_by = _licence_clears_contact(modules)
        if cleared_by is not None:
            # Vidyut, Sat 07:35: an active licence checked by number, sponsored by the
            # brokerage on record. Information only: the number is still not the office's.
            brokerage = " ".join(cleared_by.split())[:MAX_BROKERAGE_CHARS]
            lines.append(
                _line(
                    lang,
                    "label.contact",
                    CardTone.NOT_SHOWN,
                    "contact.licensed_sponsor",
                    brokerage=brokerage,
                )
            )
        elif authority.manager_on_record:
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
        # A15: on a home for sale with no property record the reason is different, and must
        # be said as it is. Whatever the ad says, we hold no phone for the brokerage.
        key = (
            "contact.no_brokerage_phone" if authority.brokerage_only else "contact.phone_unchecked"
        )
        lines.append(_line(lang, "label.contact", CardTone.NOT_CHECKED, key))
    if authority.link_domain is LinkDomain.LOOKALIKE:
        key = (
            "contact.lookalike_sender"
            if authority.lookalike_sender_only
            else "contact.lookalike_link"
        )
        lines.append(_line(lang, "label.link", CardTone.RED_FLAG, key))
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
    renter = found.number_from == "renter"
    if found.status is LicenseStatus.NOT_FOUND:
        if renter:
            # a typed number may be a typo: Not confirmed (HOLD tone), never a red flag
            return [_line(lang, label, CardTone.HOLD, "license.not_found_given")]
        return [_line(lang, label, CardTone.RED_FLAG, "license.not_found")]
    if found.status is LicenseStatus.LICENSED:
        sponsor = " ".join((found.sponsor_broker or "").split())[:MAX_SPONSOR_CHARS]
        if sponsor:
            return [_line(lang, label, CardTone.OK, "license.licensed_sponsored", broker=sponsor)]
        return [_line(lang, label, CardTone.OK, "license.licensed")]
    if found.claimed_role:
        key = "license.not_checked_given" if renter else "license.not_checked_claimed"
        return [_line(lang, label, CardTone.NOT_CHECKED, key)]
    return []  # no claim, so nothing to say


MAX_COMPANY_CHARS = 80
MAX_SOURCE_CHARS = 80


def _one_line(text: str | None, most: int) -> str:
    return " ".join((text or "").split())[:most]


def _payment_ask_flagged(modules: ModuleEvidence) -> bool:
    return any(hit.red_flag and hit.category in _PAYMENT_CATEGORIES for hit in modules.rules)


# The one rule that is not a red flag and still shows on the card (agent/rules/table.py).
MONEY_BEFORE_MOVE_IN = "fee.money_before_move_in"


def _asks_before_move_in(modules: ModuleEvidence) -> bool:
    return any(hit.rule_id == MONEY_BEFORE_MOVE_IN for hit in modules.rules)


def _rule_sits_beside_payment(modules: ModuleEvidence) -> bool:
    """The owner's rule is quoted once: beside the payment line whenever the ad asks for
    money (a flagged ask, or rent or a deposit before move-in), and on the owner line if not."""
    return _payment_ask_flagged(modules) or _asks_before_move_in(modules)


def _quoted_rule(rule: PublishedRule, lang: str, key: str) -> str:
    """The owner's own rule in its own words, with where it is published and when we read it."""
    source = rule.source_url.split("://", 1)[-1].removeprefix("www.").rstrip("/")
    return strings.text(
        key,
        lang,
        company=_one_line(rule.company, MAX_COMPANY_CHARS),
        rule=_one_line(rule.rule, 200),
        source=_one_line(source, MAX_SOURCE_CHARS),
        date=rule.checked_on.isoformat(),
    )


def _owner_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """The owner of record, beside what the poster says about owning the home (A19, #125).

    A company we know is named; any other company is "a company owner". A person never is:
    the card says "a private owner" and whether the name the poster gave matches, yes or no.
    Nothing here is a red flag, and a match is a supporting line: the owner roll is public,
    so anyone can type the owner's name.
    """
    owner = modules.owner
    if owner is None:
        return []  # no owner data: the card's standing "not checked: ownership" says so
    label = "label.owner"
    if owner.kind is OwnerKind.PERSON:
        if owner.poster_matches is OwnerMatch.YES:
            return [_line(lang, label, CardTone.OK, "owner.person_matches")]
        if not owner.poster_says_owner:
            # Someone who does not say they own it is not compared with the owner.
            return [_line(lang, label, CardTone.NOT_CHECKED, "owner.person_no_claim")]
        if owner.poster_matches is OwnerMatch.NO:
            return [_line(lang, label, CardTone.NOT_SHOWN, "owner.person_mismatch")]
        return [_line(lang, label, CardTone.NOT_CHECKED, "owner.person_no_name")]

    company = _one_line(owner.company, MAX_COMPANY_CHARS) if owner.company_known else ""
    if not company:
        # A company we do not know is never named (round 5 on #160): "a company owner".
        not_poster = _owner_is_not_the_poster(modules)
        key = "owner.company_unnamed_not_poster" if not_poster else "owner.company_unnamed"
        return [_line(lang, label, CardTone.NOT_SHOWN, key)]
    if owner.poster_matches is OwnerMatch.YES:
        tone, key = CardTone.OK, "owner.company_matches"
    elif _owner_is_not_the_poster(modules):
        tone, key = CardTone.NOT_SHOWN, "owner.company_not_poster"
    else:
        tone, key = CardTone.NOT_SHOWN, "owner.company"
    text = strings.text(key, lang, company=company)
    # The owner's rule is quoted once. Beside a flagged payment ask when there is one (it is
    # what the rule speaks to), and here otherwise.
    if owner.published_rule is not None and not _rule_sits_beside_payment(modules):
        text = f"{text} {_quoted_rule(owner.published_rule, lang, 'owner.rule')}"
    return [CardLine(label=strings.text(label, lang), text=text, tone=tone, key=label)]


def _office_declined_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    domain = modules.office_declined_domain
    if not domain:
        return []
    return [
        _line(lang, "label.office", CardTone.NOT_SHOWN, "contact.office_declined", domain=domain)
    ]


def _office_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """Someone at the office's own website domain on record confirmed this case (info line).

    The domain is the one CoStar has on record for the office, never one from the ad."""
    domain = modules.office_confirmed_domain
    if not domain:
        return []
    lines = [_line(lang, "label.office", CardTone.OK, "contact.office_confirmed", domain=domain)]
    authority = modules.authority
    if (
        authority is not None
        and authority.office_phone_match is PhoneMatch.NO
        and not modules.office_declined_domain
    ):
        # The office said yes, the headline stays Hold off, and the card says why in plain words.
        lines.append(_line(lang, "label.contact", CardTone.NOT_SHOWN, "contact.office_still_hold"))
    return lines


def _person_row(modules: ModuleEvidence, lang: str, zone: tzinfo) -> CardRow:
    return CardRow(
        kind=CardRowKind.PERSON,
        lines=[
            _here_now_line(modules, lang, zone),
            *_from_record(
                modules,
                [
                    _allowed_line(modules, lang),
                    *_office_lines(modules, lang),
                    *_office_declined_lines(modules, lang),
                    *_contact_lines(modules, lang),
                ],
            ),
            # Not from the record: the licence list is the state's, and public.
            *_license_lines(modules, lang),
            # Nor this: the owner roll is the county's, and public.
            *_owner_lines(modules, lang),
            *_record_lines(modules, lang, place=False),
            *_seen_before_lines(modules, lang, replies=True),
        ],
    )


_RECORD_SOURCE_LABEL = {
    "Texas Comptroller": "label.src_comptroller",
    "HUD": "label.src_hud",
    "City of Houston": "label.src_houston",
}


def _record_lines(modules: ModuleEvidence, lang: str, *, place: bool) -> list[CardLine]:
    """Texas public records, one neutral line each, labelled with the registry it came from.
    Information only: `decide` never reads them, and none counts as a finding either way.
    The address point is a PLACE line; the Comptroller and HUD lines are PERSON lines."""
    lines = []
    for record in modules.public_records:
        label = _RECORD_SOURCE_LABEL.get(record.source)
        if label is None or (record.key == "address_point") is not place:
            continue
        if not strings.has(f"records.{record.key}", lang):
            continue
        lines.append(
            CardLine(
                label=strings.text(label, lang),
                text=strings.text(
                    f"records.{record.key}",
                    lang,
                    company=_one_line(record.company, MAX_COMPANY_CHARS),
                    year=record.year or "",
                    zip_code=record.zip_code or "",
                ),
                tone=CardTone.NOT_CHECKED,
                source=record.data_source,
                key=label,
            )
        )
    return lines


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
    if shown >= _BOTH_MONEY_RULES:
        # Zelle and a deposit or holding fee before a viewing are one ask to the renter: one
        # line that names both, standing where the first of the two stood.
        asks = by_label["label.payment_ask"]
        both = {strings.text(f"rule.{rule_id}", lang) for rule_id in _BOTH_MONEY_RULES}
        at = next(i for i, line in enumerate(asks) if line.text in both)
        merged = _line(
            lang,
            "label.payment_ask",
            CardTone.RED_FLAG,
            "rule.payment.zelle_and_deposit_before_viewing",
        )
        rest = [line for line in asks if line.text not in both]
        by_label["label.payment_ask"] = [*rest[:at], merged, *rest[at:]]
    if not by_label["label.payment_ask"]:
        by_label["label.payment_ask"].append(_quiet_payment_line(modules, lang))
    return [line for label in _RULE_LABEL_ORDER for line in by_label[label]]


def _quiet_payment_line(modules: ModuleEvidence, lang: str) -> CardLine:
    """The payment line when no payment ask is a red flag.

    An ad that asks for rent or a deposit before move-in never reads "Matches" (conductor,
    Sat 10:03). It is a warning when the owner of record publishes how it takes money, or is
    not the poster, and "Not confirmed" otherwise. Only the tone differs: honest listings
    ask for the same thing, so this is never a flag and no verdict reads it.
    """
    if not _asks_before_move_in(modules):
        return _line(lang, "label.payment_ask", CardTone.OK, "payment.none")
    not_poster = _owner_is_not_the_poster(modules)
    has_rule = modules.owner is not None and modules.owner.published_rule is not None
    tone = CardTone.HOLD if (not_poster or has_rule) else CardTone.NOT_SHOWN
    key = "payment.before_move_in_not_owner" if not_poster else "payment.before_move_in"
    return _line(lang, "label.payment_ask", tone, key)


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
    lines = _rule_lines(modules, lang)
    rule = modules.owner.published_rule if modules.owner else None
    if rule is not None and _rule_sits_beside_payment(modules):
        # Conductor, Sat 03:00: when the ad asks for money in a way the owner's own rule
        # does not allow, the rule is quoted next to the payment line. It adds no flag and
        # changes no state: the payment ask is the flag, and DONT_PAY still needs proof.
        # Sat 10:03: the same for rent or a deposit asked before move-in, which is no flag.
        payment = strings.text("label.payment_ask", lang)
        places = [index for index, line in enumerate(lines) if line.label == payment]
        lines.insert(
            (places[-1] + 1) if places else len(lines),
            CardLine(
                label=strings.text("label.owner_rule", lang),
                key="label.owner_rule",
                text=_quoted_rule(rule, lang, "owner.rule_beside_payment"),
                tone=CardTone.HOLD,
            ),
        )
    return CardRow(kind=CardRowKind.PRICE, lines=[*lines, *_rent_lines(modules, lang)])


def _join_words(words: list[str], lang: str) -> str:
    return strings.text("list.and", lang).join(strings.text(f"kind.{word}", lang) for word in words)


def _claims_lines(modules: ModuleEvidence, lang: str) -> list[CardLine]:
    """Ad vs record: one line per note, as facts turned into the table's words. Information
    only: `decide` never reads these, and a note the table has no words for is not shown."""
    lines = []
    for note in modules.ad_notes:
        if not strings.has(f"claims.{note.key}", lang):
            continue
        claim = strings.claim_word(note.claim, note.ad_value, lang)
        label = "label.ad_claim"
        if note.pretext:
            label = "label.ad_pretext"
        elif note.key == "aerial_date":
            label = "label.aerial"
        tone = CardTone.OK if note.matches else CardTone.NOT_SHOWN
        if note.key == "aerial_date":
            tone = CardTone.NOT_CHECKED  # a date to look at, not a finding
        lines.append(
            CardLine(
                label=strings.text(label, lang),
                key=label,
                text=strings.text(
                    f"claims.{note.key}",
                    lang,
                    claim=claim,
                    record=_join_words(note.record, lang),
                    year=note.year if note.year is not None else "",
                    ad_value=note.ad_value or "",
                    record_value=note.record_value or "",
                ),
                tone=tone,
            )
        )
    return _from_record(modules, lines)


def _clean_hold_headline(
    verdict: Verdict, evidence: Evidence, rows: list[CardRow], lang: str, modules: ModuleEvidence
) -> str | None:
    """The headline for a HOLD that has nothing against it, or None. The state stays HOLD.

    Two cases, strongest first. `decide` is asked a what-if and is not changed.

    1. Everything matches: the same evidence with presence proven would be VERIFIED, and no
       line is a red flag or a warning. Only the presence step is left.
    2. Nothing goes against the record (#259): no line reads "Doesn't match" or "Warning",
       though some read "Not confirmed". On a live record "Allowed to rent it" stays not
       confirmed, so case 1 never fires there; the renter still has two things to do.
    """
    if verdict.state is not VerdictState.HOLD:
        return None
    if evidence.presence not in (PresenceStatus.NOT_REQUESTED, PresenceStatus.WAITING):
        return None
    if any(_reads_as_against(row, line) for row in rows for line in row.lines):
        return None
    if _shows_a_contradiction(modules, evidence):
        return None
    if_proven = evidence.model_copy(update={"presence": PresenceStatus.PROVEN})
    all_hold_free = not any(line.tone is CardTone.HOLD for row in rows for line in row.lines)
    if all_hold_free and decide(if_proven, lang).state is VerdictState.VERIFIED:
        return strings.text("state.hold_clean", lang)
    if modules.authority is None or modules.authority.manager_on_record is None:
        return strings.text("state.hold_nothing_against_no_office", lang)
    return strings.text("state.hold_nothing_against", lang)


def _shows_a_contradiction(modules: ModuleEvidence, evidence: Evidence) -> bool:
    """Something on the card goes against the ad though it is no red flag (XO review of #263):
    the office on record declined it, an ad claim the record contradicts, an owner who is not
    the poster, a poster who is not the manager on record, or a phone that is not the office's.
    A changed phone is a tamper we show catching, so it never lands on the reassuring line.
    The aerial date and the ad's own excuses are information, not a contradiction."""
    authority = modules.authority
    return (
        evidence.office_declined_domain is not None
        or evidence.owner_flag
        or any(
            not note.matches and not note.pretext and note.key != "aerial_date"
            for note in modules.ad_notes
        )
        or (
            authority is not None
            and (
                authority.status is AuthorityStatus.MISMATCH
                or authority.office_phone_match is PhoneMatch.NO
            )
        )
    )


def _reads_as_against(row: CardRow, line: CardLine) -> bool:
    """The line would be shown as "Doesn't match" or "Warning": a red flag anywhere, or a
    warning outside the PERSON row (there a hold reads "Not confirmed", e.g. no reply yet)."""
    if line.tone is CardTone.RED_FLAG:
        return True
    return line.tone is CardTone.HOLD and row.kind is not CardRowKind.PERSON


def _red_flag_headline(verdict: Verdict, rows: list[CardRow], lang: str) -> str | None:
    """The headline for a HOLD that carries a red-flag line, or None.

    The state stays HOLD (decide is untouched); only the words say why, so a red-flag ad does
    not read like an honest one. Money is named before papers, and papers before pressure.
    """
    if verdict.state is not VerdictState.HOLD:
        return None
    red = [line for row in rows for line in row.lines if line.tone is CardTone.RED_FLAG]
    if not red:
        return None
    labels = {line.label for line in red}
    for label, key in (
        ("label.payment_ask", "state.hold_red_money"),
        ("label.data_ask", "state.hold_red_papers"),
        ("label.pressure", "state.hold_red_pressure"),
    ):
        if strings.text(label, lang) in labels:
            return strings.text(key, lang)
    return strings.text("state.hold_red", lang)


def _no_photos_headline(verdict: Verdict, modules: ModuleEvidence, lang: str) -> str | None:
    """The plain hold line for an UNVERIFIED case where no listing photo was sent, or None.

    "Could not place these photos" is for photos that were sent and did not place. With none
    sent, the card must not talk about placing them (the state word stays UNVERIFIED).
    """
    if verdict.state is not VerdictState.UNVERIFIED:
        return None
    if modules.locate is not None and modules.locate.photos:
        return None
    return strings.text("state.hold", lang)


def headline_text(card: Card) -> str:
    """The words at the top of a card: its own headline when it has one, else its state's.
    The PNG (card/render.py) reads it the same way."""
    return card.headline or strings.text(f"state.{card.state.value}", card.lang)


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
    evidence = to_evidence(modules, lang)
    verdict = decide(evidence, lang)
    public_id = modules.case_id.removeprefix(FIXTURE_ID_PREFIX)
    checked = _aware(checked_at, "checked_at") if checked_at is not None else datetime.now(UTC)
    for spot in modules.challenge.spots if modules.challenge else []:
        if spot.replied_at is not None:
            _aware(spot.replied_at, f"replied_at of spot {spot.spot_id}")

    verify_url = None
    if verify_base_url:
        verify_url = f"{verify_base_url.rstrip('/')}/c/{public_id}"

    rows = [
        _place_row(modules, lang),
        _person_row(modules, lang, checked.tzinfo),
        _price_row(modules, lang),
    ]
    claims = _claims_lines(modules, lang)
    if claims:  # only when there is something to say; the three rows above are always there
        rows.append(CardRow(kind=CardRowKind.CLAIMS, lines=claims))

    summary, checks_out, does_not = _summary(modules, verdict, rows, lang)

    return Card(
        case_id=public_id,
        source=modules.source,
        state=verdict.state,
        headline=_clean_hold_headline(verdict, evidence, rows, lang, modules)
        or _red_flag_headline(verdict, rows, lang)
        or _no_photos_headline(verdict, modules, lang),
        checked_at=checked,
        expires_at=checked + CARD_TTL,
        rows=rows,
        not_checked=[
            strings.text("not_checked.id", lang),
            strings.text("not_checked.lease", lang),
            # Ownership stays on the list unless the owner of record was compared (A19).
            *([] if _ownership_compared(modules, lang) else [_ownership_item(lang)]),
        ],
        footer=[
            strings.text("footer.two_rules", lang),
            strings.text("footer.only_trust", lang),
        ],
        verify_url=verify_url,
        lang=lang,
        for_sale=_for_sale_finding(modules),
        summary=summary,
        checks_out=checks_out,
        does_not=does_not,
    )


SUMMARY_SENTENCES = 3
_DOES_NOT_TONES = (CardTone.RED_FLAG, CardTone.HOLD, CardTone.NOT_SHOWN)


def _price_gap(modules: ModuleEvidence, lang: str) -> str | None:
    """How far under the building's own listing the asked rent is. The percent is ours; the
    record's rents stay off the card."""
    price = modules.price
    if price is None or price.status is not PriceStatus.BELOW_RANGE:
        return None
    if not (price.record_min and price.listed_rent):
        return None
    percent = round(100 * (price.record_min - price.listed_rent) / price.record_min)
    if percent <= 0:
        return None
    if price.compared_beds is None:
        return strings.text("summary.price_gap_any", lang, percent=percent)
    beds = price.compared_beds
    plan = (
        strings.text("rent.plan.studio", lang)
        if beds == 0
        else strings.text("rent.plan.beds", lang, beds=beds)
    )
    return strings.text("summary.price_gap", lang, percent=percent, plan=plan)


# What each of decide()'s reasons is worth to a renter, for ordering the short why: a red flag
# or proof (rank 0), something not confirmed (1), or good news (2). The reasons arrive as text,
# so they are matched back to their keys; a blank in one ({n}, {domain}) matches anything.
_RED_REASONS = (
    "reason.forged",
    "reason.forged_copy",
    "reason.forged_copy_unknown",
    "reason.photo_elsewhere",
    "reason.price_flag",
    "reason.payment_flag",
    "reason.rule_flag",
    "reason.for_sale",
    "reason.lookalike_link",
    "reason.unit_flag",
    "reason.aerial_wrong_building",
    "reason.license_not_found",
)
_GOOD_REASONS = (
    "reason.located",
    "reason.authority_matches",
    "reason.authority_matches_brokerage",
    "reason.presence_proven",
    "reason.office_confirmed",
)


def _is_reason(sentence: str, key: str, lang: str) -> bool:
    blank = "\x00"
    head, _, tail = strings.text(key, lang, n=blank, domain=blank).partition(blank)
    return sentence.startswith(head) and sentence.endswith(tail or "")


def _reason_rank(sentence: str, lang: str) -> int:
    """0 red flag or proof, 1 not confirmed, 2 good news."""
    if any(_is_reason(sentence, key, lang) for key in _RED_REASONS):
        return 0
    if any(_is_reason(sentence, key, lang) for key in _GOOD_REASONS):
        return 2
    return 1


def _summary(
    modules: ModuleEvidence, verdict: Verdict, rows: list[CardRow], lang: str
) -> tuple[list[str], list[str], list[str]]:
    """Proof plan 3.2: the short why, what checks out, what does not. Code only, deterministic.

    The sentences are decide()'s own reasons. Under a result that did not pass they lead with
    the red flags (the measured rent gap first, standing in for the generic price reason), then
    what is not confirmed, and never include good news: "why this is not a good deal" does not
    list what is fine. A result that passed keeps decide()'s order. Nothing here chooses a
    state, and no sentence names a person."""
    gap = _price_gap(modules, lang)
    reasons = list(verdict.reasons)
    if gap:
        generic_price = strings.text("reason.price_flag", lang)
        reasons = [gap if r == generic_price else r for r in reasons]
    if verdict.state is VerdictState.VERIFIED:
        sentences = reasons[:SUMMARY_SENTENCES]
    else:
        # sorted() is stable, so decide()'s order holds inside each rank.
        ranked = sorted(
            (r for r in reasons if r == gap or _reason_rank(r, lang) < 2),
            key=lambda r: -1 if r == gap else _reason_rank(r, lang),
        )
        sentences = (ranked or reasons)[:SUMMARY_SENTENCES]
    lines = [line for row in rows for line in row.lines]
    checks_out = [f"{ln.label}: {ln.text}" for ln in lines if ln.tone is CardTone.OK]
    does_not = [f"{ln.label}: {ln.text}" for ln in lines if ln.tone in _DOES_NOT_TONES]
    return sentences, checks_out, does_not


def _ownership_item(lang: str) -> str:
    return strings.text("not_checked.ownership", lang)


def _ownership_compared(modules: ModuleEvidence, lang: str) -> bool:
    """The card has an owner-of-record line that says something, not just "not checked"."""
    return any(line.tone is not CardTone.NOT_CHECKED for line in _owner_lines(modules, lang))


def _for_sale_finding(modules: ModuleEvidence) -> ForSaleMatch | None:
    """The for-sale lookup, when it found something. "Looked up, nothing" is not a finding."""
    found = modules.for_sale
    if found is None or found.status is ForSaleStatus.NONE:
        return None
    return found

"""A20 (#126): the "Report this copy" evidence pack.

A listing agent whose listing was copied has to ask the platform to take the copy down. This
builds the one pack they take there: what the home's own record says, the reasons the check
gave, which photos were matched, and where to click on each platform.

Everything in it is a fact from code:

- the proof lines are `decide()`'s own reasons, the fixed strings in `card/strings.py`, and
  only the ones about the listing and the record (an allowlist). A reason that came from
  the renter's own thread, such as a payment ask, never goes in a pack someone else pastes;
- the status strip is what the card already carries in `for_sale`;
- photos are named by their number, and pictures are only ever references to our own routes.

What is never in it: a match score, an inlier count or a threshold; a phone hash, a photo hash
or a model id; image bytes; anything about the renter (no renter id, none of the text they
sent); and a word about any person. A case is "reportable" only on proof or on a record that
shows the home for sale. A hold on something not confirmed hands nobody report steps: the
poster may be a real agent (conductor, Sat 03:15). Nor does a home for sale whose ad carries
the office's own phone on record: that is the brokerage offering it (ruling, Sat 03:36).
"""

from snapback.card import strings
from snapback.contracts import (
    Card,
    ForSaleStatus,
    LocateStatus,
    MemoryHitKind,
    ModuleEvidence,
    PhoneMatch,
    ReportPhotoPair,
    ReportPlatform,
    ReportResponse,
    ReportSource,
    ReportStatusStrip,
    ReportSteps,
    VerdictState,
)
from snapback.verdict import _photo_number, decide, presence_of, to_evidence

MAX_BROKERAGE_CHARS = 80

# The reasons that may go in a pack: facts about the listing and the record. Everything else
# decide() says stays out. What the renter was asked for (a payment, a fee, pressure) is from
# their own thread; who the poster is, presence and where photos were placed are about the
# check, and the card is where those are read. The owner and licence reasons are listed for
# when those rules are on main; a key the table does not have is skipped.
_PACK_REASONS = (
    "reason.for_sale",
    "reason.photo_elsewhere",
    "reason.license_not_found",
    "reason.owner_not_poster",
)
MAX_STEPS = 5
MAX_PAIRS = 40


def _one_line(text: str, most: int) -> str:
    return " ".join(text.split())[:most]


def _status_strip(card: Card) -> ReportStatusStrip | None:
    """What the home's own record says, exactly as far as the card already says it."""
    found = card.for_sale
    if found is None or found.status is ForSaleStatus.NONE:
        return None
    offices = [_one_line(name, MAX_BROKERAGE_CHARS) for name in found.offices if name.strip()]
    return ReportStatusStrip(
        status=found.status,
        site=found.site,
        listed_on=found.listed_on,
        changed_on=found.changed_on,
        brokerage=offices[0] if offices else None,
    )


def _photo_pairs(modules: ModuleEvidence, lang: str) -> list[ReportPhotoPair]:
    """The listing photos something was found about, by number. No picture, no score."""
    pairs: dict[int, ReportPhotoPair] = {}
    for hit in modules.memory:
        number = _photo_number(modules, hit.matched_listing_photo_id)
        if hit.hit is MemoryHitKind.SAME_CASE_LISTING and number is not None:
            pairs[number] = ReportPhotoPair(
                listing_photo=number, finding=strings.text("reason.forged_copy", lang, n=number)
            )
    photos = modules.locate.photos if modules.locate else []
    for number, photo in enumerate(photos, start=1):
        if photo.status is LocateStatus.LOCATED_ELSEWHERE and number not in pairs:
            pairs[number] = ReportPhotoPair(
                listing_photo=number, finding=strings.text("report.pair.elsewhere", lang, n=number)
            )
    return [pairs[number] for number in sorted(pairs)][:MAX_PAIRS]


def _proof_lines(modules: ModuleEvidence, reasons: list[str], lang: str) -> list[str]:
    """decide()'s reasons, in its order, less everything not on the allowlist."""
    allowed = {strings.text(key, lang) for key in _PACK_REASONS if strings.has(key, lang)}
    if presence_of(modules).copies_listing_photo:
        # "The reply is a copy of listing photo 2." names the photo, so it is the sentence
        # the evidence carries, not a fixed key.
        copied = to_evidence(modules, lang).forgery_reason
        if copied:
            allowed.add(copied)
    return [reason for reason in reasons if reason in allowed]


def _steps(platform: ReportPlatform, lang: str) -> ReportSteps:
    steps = []
    for number in range(1, MAX_STEPS + 1):
        key = f"report.steps.{platform.value}.{number}"
        if not strings.has(key, lang):
            break
        steps.append(strings.text(key, lang))
    return ReportSteps(
        platform=platform,
        name=strings.text(f"report.platform.{platform.value}", lang),
        steps=steps,
    )


_PUBLIC_SOURCES = ("HUD", "Census", "RDAP")


def _source_names(card: Card) -> list[str]:
    names = [ln.source_name for row in card.rows for ln in row.lines if ln.source_name]
    return list(dict.fromkeys(names))


def _public_sources(card: Card) -> list[ReportSource]:
    """The lines a public source answered, each with its source's name and LIVE or FIXTURE."""
    return [
        ReportSource(
            source_name=ln.source_name,
            label=ln.label,
            text=ln.text,
            data_source=ln.source or card.source,
        )
        for row in card.rows
        for ln in row.lines
        if ln.source_name in _PUBLIC_SOURCES
    ]


def build_report(
    modules: ModuleEvidence, card: Card, *, case_id: str, lang: str, aerial: bool
) -> ReportResponse:
    """The pack for one case. `card` is the case's own card; `aerial` says whether the case
    names a building, so its aerial proof route has something to show."""
    verdict = decide(to_evidence(modules, lang), lang)
    strip = _status_strip(card)
    # The ad's phone is the office's on record: the brokerage itself is offering the home,
    # so a for-sale record is not a copy to report (ruling, Sat 03:36).
    by_the_office = (
        modules.authority is not None and modules.authority.office_phone_match is PhoneMatch.YES
    )
    for_sale = strip is not None and strip.status is ForSaleStatus.ACTIVE and not by_the_office
    reportable = verdict.state is VerdictState.DONT_PAY or for_sale

    placed = {LocateStatus.LOCATED_IN_CLAIMED, LocateStatus.LOCATED_ELSEWHERE}
    photos = modules.locate.photos if modules.locate else []
    any_placed = any(photo.status in placed for photo in photos)

    return ReportResponse(
        case_id=case_id,
        source=modules.source,
        lang=lang,
        checked_at=card.checked_at,
        state=verdict.state,
        reportable=reportable,
        status_strip=strip,
        proof_lines=_proof_lines(modules, verdict.reasons, lang),
        photo_pairs=_photo_pairs(modules, lang) if reportable else [],
        twin_url=f"/case/{case_id}/twin" if any_placed else None,
        aerial_url=f"/cases/{case_id}/aerial" if aerial else None,
        platforms=[_steps(platform, lang) for platform in ReportPlatform] if reportable else [],
        not_checked=list(card.not_checked),
        source_names=_source_names(card),
        sources=_public_sources(card),
    )

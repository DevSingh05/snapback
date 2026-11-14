"""A20 (#126): the "Report this copy" evidence pack.

A listing agent whose listing was copied has to ask the platform to take the copy down. This
builds the one pack they take there: what the home's own record says, the reasons the check
gave, which photos were matched, and where to click on each platform.

Everything in it is a fact from code:

- the proof lines are `decide()`'s own reasons, the fixed strings in `card/strings.py`;
- the status strip is what the card already carries in `for_sale`;
- photos are named by their number, and pictures are only ever references to our own routes.

What is never in it: a match score, an inlier count or a threshold; a phone hash, a photo hash
or a model id; image bytes; anything about the renter (no renter id, none of the text they
sent); and a word about any person. A case is "reportable" only on proof or on a record that
shows the home for sale. A hold on something not confirmed hands nobody report steps: the
poster may be a real agent (conductor, Sat 03:15).
"""

from snapback.card import strings
from snapback.contracts import (
    Card,
    ForSaleStatus,
    LocateStatus,
    MemoryHitKind,
    ModuleEvidence,
    ReportPhotoPair,
    ReportPlatform,
    ReportResponse,
    ReportStatusStrip,
    ReportSteps,
    VerdictState,
)
from snapback.verdict import _photo_number, decide, to_evidence

MAX_BROKERAGE_CHARS = 80
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


def build_report(
    modules: ModuleEvidence, card: Card, *, case_id: str, lang: str, aerial: bool
) -> ReportResponse:
    """The pack for one case. `card` is the case's own card; `aerial` says whether the case
    names a building, so its aerial proof route has something to show."""
    verdict = decide(to_evidence(modules, lang), lang)
    strip = _status_strip(card)
    for_sale = strip is not None and strip.status is ForSaleStatus.ACTIVE
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
        proof_lines=list(verdict.reasons),
        photo_pairs=_photo_pairs(modules, lang) if reportable else [],
        twin_url=f"/case/{case_id}/twin" if any_placed else None,
        aerial_url=f"/cases/{case_id}/aerial" if aerial else None,
        platforms=[_steps(platform, lang) for platform in ReportPlatform] if reportable else [],
        not_checked=list(card.not_checked),
    )

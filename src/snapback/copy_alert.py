"""Your listing is being copied: a draft note for the leasing office on record.

Built from the same data as the real-listing panel (`real_listing`). It is a draft and nothing
here can send it: this module imports no mail or network client (AGENTS.md rule 8: humans send
outbound messages), as `office/proof.py` does not either. It fires only on facts:

- some of the ad's photos were placed in that building's scan (proof); and
- for the building the ad names, the ad's phone is not the office's on record. For a different
  building the photos were placed in, the phone is not compared (the record's phone belongs to
  the building the ad names), so the note says nothing about the phone.

The note never names a person, never says scam, and carries no phone digits, street address or
record rent: the rent is a percent. Words come from card/strings.py (`copy.*`).
"""

from snapback.card import strings
from snapback.contracts import (
    CopyAlert,
    ModuleEvidence,
    PhoneMatch,
    PropertyRecord,
    RealListing,
)
from snapback.real_listing import real_listing, rent_percent_under
from snapback.settings import Settings


def _off(modules: ModuleEvidence, case_id: str, why: str, lang: str, **fields) -> CopyAlert:
    return CopyAlert(
        case_id=case_id,
        source=modules.source,
        fires=False,
        why_not=why,
        as_of=strings.text("real.as_of", lang),
        **fields,
    )


def copy_alert(
    modules: ModuleEvidence,
    claimed: PropertyRecord | None,
    matched: PropertyRecord | None,
    settings: Settings,
    *,
    case_id: str,
    ad_beds: int | None = None,
    ad_unit: str | None = None,
    report_ready: bool = False,
    lang: str = strings.DEFAULT_LANG,
) -> CopyAlert:
    panel: RealListing | None = real_listing(
        modules, claimed, matched, settings, ad_beds=ad_beds, ad_unit=ad_unit, lang=lang
    )
    if panel is None:
        return _off(modules, case_id, "no_record", lang)
    shown = {
        "which": panel.which,
        "property_id": panel.property_id,
        "manager_company": panel.manager_company,
        "website_host": panel.website_host,
        "photos_in_scan": panel.photos_in_scan,
        "photos_total": panel.photos_total,
        "phone_is_office": panel.phone_is_office,
    }
    if panel.photos_in_scan < 1:
        return _off(modules, case_id, "no_photos_in_scan", lang, **shown)
    if panel.which == "claimed":
        if panel.phone_is_office is PhoneMatch.YES:
            return _off(modules, case_id, "phone_is_office", lang, **shown)
        if panel.phone_is_office is not PhoneMatch.NO:
            return _off(modules, case_id, "phone_not_checked", lang, **shown)

    record = matched if panel.which == "matched" else claimed
    percent = rent_percent_under(record, panel.ad_rent, ad_beds, ad_unit)

    to = (
        strings.text("copy.to_company", lang, company=panel.manager_company)
        if panel.manager_company
        else strings.text("copy.to_office", lang)
    )
    scan_key = "copy.photos_matched" if panel.which == "matched" else "copy.photos_claimed"
    parts = [strings.text(scan_key, lang, n=panel.photos_in_scan, m=panel.photos_total)]
    if panel.which == "claimed":
        parts.append(strings.text("copy.phone_not_office", lang))
    if percent is not None:
        parts.append(strings.text("copy.rent_under", lang, percent=percent))
    report_url = f"/cases/{case_id}/report"
    paragraphs = [to, " ".join(parts), strings.text("copy.ask", lang)]
    # The note points to the evidence pack only once there is one to point to.
    if report_ready:
        report = strings.text("copy.report_name", lang)
        paragraphs.append(strings.text("copy.report_line", lang, report=report))
    paragraphs.append(strings.text("copy.draft_only", lang))
    body = "\n\n".join(paragraphs)
    return CopyAlert(
        case_id=case_id,
        source=modules.source,
        fires=True,
        rent_percent_under=percent,
        draft_subject=strings.text("copy.subject", lang),
        draft_body=body,
        report_url=report_url,
        report_ready=report_ready,
        as_of=strings.text("real.as_of", lang),
        **shown,
    )

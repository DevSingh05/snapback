"""Walk it first, W4: the scan label and date on the door stop, the door tip, the aerial date."""

from datetime import date

from snapback.contracts import DataSource
from snapback.tour import (
    AGE_NOTE,
    DOOR_TIP,
    NO_SCAN_DATE,
    SCAN_APARTMENT,
    SCAN_HOUSE,
    TourSweep,
    build_tour,
)

Q = (0.0, 0.0, 0.0, 1.0)
SWEEPS = [
    TourSweep("s00", (0.0, 1.4, 0.0), Q, "Entryway"),
    TourSweep("s01", (3.0, 1.4, 0.0), Q, "Kitchen"),
]
TODAY = date(2026, 11, 14)


def plan(**kw):
    args = dict(
        property_id="fx-prop-3",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=SWEEPS,
        has_scan=True,
        today=TODAY,
    )
    args.update(kw)
    return build_tour(**args)


def test_scan_date_reads_month_and_year_with_its_source():
    p = plan(scan_on=date(2026, 3, 14))
    assert p.scan_date_line == "Scanned Mar 2026 (Matterport)"
    assert p.scan_age_note is None


def test_a_scan_older_than_twelve_months_carries_the_change_note():
    p = plan(scan_on=date(2025, 10, 1))
    assert p.scan_date_line == "Scanned Oct 2025 (Matterport)"
    assert p.scan_age_note == AGE_NOTE
    assert "check finishes in person" in AGE_NOTE


def test_exactly_twelve_months_old_is_not_yet_old():
    assert plan(scan_on=date(2025, 11, 14)).scan_age_note is None
    assert plan(scan_on=date(2025, 11, 13)).scan_age_note == AGE_NOTE


def test_no_scan_date_says_so_and_never_invents_one():
    p = plan()
    assert p.scan_date_line == NO_SCAN_DATE == "Scan date not on record"
    assert p.scan_age_note is None


def test_no_scan_means_no_scan_date_line():
    p = plan(has_scan=False, sweeps=[], scan_on=date(2026, 3, 14))
    assert p.scan_date_line is None and p.scan_age_note is None


def test_door_stop_names_what_kind_of_scan_it_is():
    assert plan(kind="apartment").scan_label == SCAN_APARTMENT
    assert "model unit" in SCAN_APARTMENT and "in this building" in SCAN_APARTMENT
    assert plan(kind="house").scan_label == SCAN_HOUSE == "a 3D scan of this home"


def test_door_tip_names_the_address_or_unit_number_with_and_without_an_entry_room():
    labelled = plan()
    numbered = plan(sweeps=[TourSweep("s00", (0.0, 1.4, 0.0), Q, None)])
    for p in (labelled, numbered):
        door = next(s for s in p.stops if s.kind == "door")
        assert door.tip == DOOR_TIP
    assert "address (or unit number)" in DOOR_TIP and "lease" in DOOR_TIP


def test_aerial_date_line_names_vexcel_and_the_day():
    p = plan(aerial_on=date(2025, 3, 14), aerial_image=True)
    arrive = p.stops[0]
    assert any(f.text == "Aerial photo captured Mar 14, 2025" and f.source for f in arrive.facts)
    assert p.aerial and p.aerial.captured_on == date(2025, 3, 14)


def test_new_walk_copy_has_no_banned_words_or_dashes():
    p = plan(scan_on=date(2024, 1, 5))
    text = " ".join(
        [p.scan_date_line or "", p.scan_age_note or "", DOOR_TIP, NO_SCAN_DATE, AGE_NOTE]
    ).lower()
    for word in ("available", "for rent", "book", "everything", "—", "–"):
        assert word not in text

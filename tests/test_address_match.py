"""#8 proof run: a typed street address joins the kit record it names, exactly or not at all.

All addresses and records here are synthetic. Nothing reaches the network: the store's public
lookups find nothing (no keys), so only the address join is under test.
"""

from snapback.agent.address_match import build_index, match_address, street_key
from snapback.agent.intake import read_listing
from snapback.agent.join import KitLookups, record_for_address
from snapback.api.cases import CaseStore
from snapback.contracts import DataSource, PropertyRecord
from snapback.settings import Settings


def _record(pid: str, address: str | None) -> PropertyRecord:
    return PropertyRecord(
        property_id=pid,
        source=DataSource.LIVE,
        market="Houston",
        street_address=address,
        building_name=f"Example {pid}",
        website_host=f"{pid}.example",
    )


OAK = _record("fx-oak", "1400 Example Oak Street, Houston, TX 77096")
ELM = _record("fx-elm", "22 N Example Elm Blvd, Houston, TX 770321234")  # 9-digit ZIP
TWIN_A = _record("fx-twin-a", "500 Example Twin Ave, Houston, TX 77002")
TWIN_B = _record("fx-twin-b", "500 Example Twin Avenue, Houston, TX 77002")
NO_ADDRESS = _record("fx-none", None)
INDEX = build_index([OAK, ELM, TWIN_A, TWIN_B, NO_ADDRESS])


def test_street_key_spells_suffixes_and_directions_one_way():
    assert street_key("1400 Example Oak Street") == ("1400", "example oak st")
    assert street_key("22 North Example Elm Boulevard") == ("22", "n example elm blvd")
    assert street_key("Example Oak St") is None  # no house number


def test_the_ad_address_finds_its_record_however_the_suffix_is_written():
    ad = "2 bed at 1400 Example Oak St, Houston, TX 77096. Text 713-555-0142."
    assert match_address(ad, INDEX) is OAK


def test_a_nine_digit_zip_on_the_record_matches_a_five_digit_one_in_the_ad():
    ad = "Studio, 22 North Example Elm Boulevard, Houston TX 77032, tours daily."
    assert match_address(ad, INDEX) is ELM


def test_a_different_zip_is_no_match():
    ad = "2 bed at 1400 Example Oak St, Houston, TX 77002."
    assert match_address(ad, INDEX) is None


def test_an_ad_with_no_zip_still_matches_on_number_and_street():
    ad = "Room at 1400 Example Oak Street, Houston, Texas, $700."
    assert match_address(ad, INDEX) is OAK


def test_two_records_at_one_address_is_no_match():
    ad = "Loft at 500 Example Twin Ave, Houston, TX 77002."
    assert match_address(ad, INDEX) is None


def test_a_wrong_house_number_or_no_address_is_no_match():
    assert match_address("2 bed at 1402 Example Oak St, Houston, TX 77096.", INDEX) is None
    assert match_address("Nice 2 bed near the park, text me.", INDEX) is None


def test_a_fixture_kit_never_matches():
    lookups = KitLookups(DataSource.FIXTURE)
    assert lookups.record_for_address("2 bed at 1400 Example Oak St, Houston, TX 77096.") is None


class _Lookups:
    """A kit of two records whose address match is the real one."""

    def record(self, pid):
        return {OAK.property_id: OAK, ELM.property_id: ELM}.get(pid)

    def records(self):
        return {OAK.property_id: OAK, ELM.property_id: ELM}

    def record_for_address(self, text):
        return match_address(text, build_index([OAK, ELM]))

    def __getattr__(self, name):  # any other lookup finds nothing
        return lambda *a, **k: None


class _Broken(_Lookups):
    def record_for_address(self, text):
        raise RuntimeError("index broke")


def _store(lookups) -> CaseStore:
    conf = Settings(
        _env_file=None,
        snapback_data_source=DataSource.LIVE,
        brightdata_api_token=None,
        apify_token=None,
        browser_use_api_key=None,
    )
    return CaseStore(conf, lookups=lookups)


def _listing(text: str):
    return read_listing(text, ocr=lambda blob: "")


def test_a_typed_address_runs_the_case_on_that_buildings_record():
    ad = "1 bed at 1400 Example Oak St, Houston, TX 77096, tours daily. 713-555-0142"
    case = _store(_Lookups()).create(_listing(ad))
    assert case.office_record is OAK
    assert case.case_id and not case.case_id.startswith("fx-")  # a LIVE case id


def test_an_address_the_kit_does_not_hold_runs_on_no_record():
    ad = "Room at 77 Example Nowhere Rd, Houston, TX 77002, $650. 713-555-0119"
    case = _store(_Lookups()).create(_listing(ad))
    assert case.office_record is None


def test_a_property_id_still_wins_over_the_typed_address():
    ad = "1 bed at 1400 Example Oak St, Houston, TX 77096."
    case = _store(_Lookups()).create(_listing(ad), ELM.property_id)
    assert case.office_record is ELM


def test_a_lookup_that_breaks_is_no_match_and_the_check_still_runs():
    ad = "1 bed at 1400 Example Oak St, Houston, TX 77096."
    assert record_for_address(_Broken(), ad) is None
    case = _store(_Broken()).create(_listing(ad))
    assert case.office_record is None

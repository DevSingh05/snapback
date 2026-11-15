"""#351: a text-only ad that names one building exactly gets its links compared with that
building's site. No record is joined. All names and hosts here are synthetic."""

from snapback.agent.address_match import build_name_index, website_for_name
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules
from snapback.contracts import DataSource, LinkDomain, PropertyRecord


def _rec(pid, name, host="exampleliving.com"):
    return PropertyRecord(
        property_id=pid,
        source=DataSource.LIVE,
        market="Houston",
        building_name=name,
        website_host=host,
    )


GREEN = _rec("fx-green", "Example Greenbriar")
PARK = _rec("fx-park", "Example Greenbriar Park", "examplegreenbriarpark.com")
NO_SITE = _rec("fx-gardens", "Example Greenbriar Gardens", None)
INDEX = build_name_index(
    [
        GREEN,
        PARK,
        NO_SITE,
        _rec("fx-short", "The Oaks", "oaksliving.com"),
        _rec("fx-d1", "Example Twin"),
        _rec("fx-d2", "Example Twin"),
    ]
)


class _Kit:
    def __init__(self, index=INDEX, broken=False):
        self._index, self._broken = index, broken

    def website_for_name(self, text):
        if self._broken:
            raise RuntimeError("index broke")
        return website_for_name(text, self._index)

    def __getattr__(self, name):
        return lambda *a, **k: None


def _link(link, kit=None, name="Example Greenbriar", rdap_down=True):
    text = f"1 bed at {name}, $1,585/month. Apply on {link}. Text 713-555-0142."
    listing = read_listing(text, ocr=lambda blob: "")
    modules = JoinedModules(
        stand_in=None,
        listing=listing,
        record=None,
        for_sale=None,
        license=None,
        owner=None,
        place_check=None,
        domain_check=None,
        salt="s",
        record_source=DataSource.LIVE,
        lookups=kit or _Kit(),
    )
    return modules.authority("c").link_domain


def test_text_only_ad_with_a_lookalike_link_gets_the_flag_even_with_rdap_down():
    assert _link("https://exampleliving.co/apply") is LinkDomain.LOOKALIKE
    assert _link("https://exammpleliving.com") is LinkDomain.LOOKALIKE


def test_the_exact_host_gets_no_flag():
    assert _link("https://exampleliving.com/apply") is LinkDomain.NOT_CHECKED


def test_no_matching_building_is_unchanged():
    assert _link("https://exampleliving.co", name="Some Other Place") is LinkDomain.NOT_CHECKED


def test_a_lookup_that_breaks_is_unchanged():
    assert _link("https://exampleliving.co", _Kit(broken=True)) is LinkDomain.NOT_CHECKED


def test_a_short_generic_name_never_matches():
    assert website_for_name("2 bed at The Oaks apartments", INDEX) is None
    assert website_for_name("2 bed at Example Greenbrier", INDEX) is None  # not fuzzy


def test_two_buildings_with_one_name_is_no_match():
    assert website_for_name("1 bed at Example Twin", INDEX) is None
    assert website_for_name("1 bed at example greenbriar suites", INDEX) == "exampleliving.com"


def test_a_name_inside_a_longer_buildings_name_never_matches():
    # "Example Greenbriar Park" is its own building: its own site is not a lookalike of ours.
    assert (
        website_for_name("1 bed at Example Greenbriar Park", INDEX) == "examplegreenbriarpark.com"
    )
    assert _link("https://examplegreenbriarpark.com", name="Example Greenbriar Park") is (
        LinkDomain.NOT_CHECKED
    )
    # A longer building with no website still blocks the shorter name.
    assert website_for_name("1 bed at Example Greenbriar Gardens", INDEX) is None

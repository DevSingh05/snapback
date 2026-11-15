"""W1 hookup: what a live case hands the web checks, and that the store starts them only when
the flag is on. Nothing here reaches the network: no keys are set, so every check reads
"not checked" without a call."""

from snapback.agent.intake import read_listing
from snapback.agent.rules.contact import phone_hash
from snapback.agent.web.facts import CheckStatus
from snapback.agent.web.inputs import plan_words, web_inputs_for
from snapback.api.cases import CaseStore
from snapback.contracts import DataSource, PropertyRecord
from snapback.settings import Settings

SALT = "test-salt"
AD = (
    "Spacious 2 bed in a quiet building near the park with a balcony and parking, $1,050 a "
    "month. Text 713-555-0142 or mail owner@pay.example. Apply at "
    "https://oakcourtt.example/apply?ref=renter-77 today."
)
RECORD = PropertyRecord(
    property_id="fx-web-1",
    source=DataSource.LIVE,
    market="Houston",
    lat=29.70123,
    lon=-95.41267,
    website_host="oakcourt.example",
    site_phone_hash=phone_hash("713-555-0199", SALT),
)


def listing():
    return read_listing(AD, ocr=lambda blob: "")


def test_inputs_carry_hosts_hashes_and_a_rounded_area_only():
    given = web_inputs_for(listing(), RECORD, SALT)
    assert given.ad_link == "https://oakcourtt.example/"  # no path, no ?ref=
    assert given.website_host == "oakcourt.example"
    assert given.center == (29.7, -95.41)
    assert given.ad_phone_hash == phone_hash("713-555-0142", SALT)
    assert given.site_phone_hash == RECORD.site_phone_hash
    assert given.beds == 2 and given.city == "Houston"
    phrase = given.ad_phrase or ""
    assert phrase and "555" not in phrase and "@" not in phrase and "http" not in phrase
    dumped = given.model_dump_json()
    assert "0142" not in dumped and "renter-77" not in dumped and "owner@" not in dumped


def test_no_record_means_no_site_and_no_area():
    given = web_inputs_for(listing(), None, SALT)
    assert given.website_host is None and given.center is None and given.site_phone_hash is None
    assert given.ad_link == "https://oakcourtt.example/"


def test_plan_words_for_a_studio_and_a_unit():
    studio = read_listing("Studio apartment, unit 4B, $900 a month.", ocr=lambda blob: "")
    words = plan_words(studio)
    assert "studio" in words
    if studio.unit:
        assert f"unit {studio.unit}" in words


class _Lookups:
    def record(self, pid):
        return RECORD if pid == RECORD.property_id else None

    def records(self):
        return {RECORD.property_id: RECORD}

    def for_sale(self, text):
        return None

    def for_sale_at(self, text, lat, lon):
        return None

    def __getattr__(self, name):  # any other lookup finds nothing
        return lambda *a, **k: None


def _store(**over):
    conf = Settings(
        _env_file=None,
        snapback_data_source=DataSource.LIVE,
        brightdata_api_token=None,
        apify_token=None,
        browser_use_api_key=None,
        **over,
    )
    return CaseStore(conf, lookups=_Lookups())


def test_flag_off_starts_no_web_checks():
    case = _store().create(listing(), RECORD.property_id)
    assert case.session.web_facts is None


def test_flag_on_starts_them_on_a_live_case_and_they_land_in_the_trace():
    case = _store(snapback_web_checks=True).create(listing(), RECORD.property_id)
    assert case.session.web_facts is not None
    import time

    end = time.monotonic() + 5
    while case.session.web_facts() is None and time.monotonic() < end:
        time.sleep(0.05)
    facts = case.session.web_facts()
    assert facts is not None and facts.source is DataSource.LIVE
    assert facts.site.status is CheckStatus.NOT_CHECKED  # no keys, so no call
    picks = [e.pick for e in case.session.trace.events if (e.pick or "").startswith("web.")]
    assert sorted(picks) == ["web.elsewhere", "web.link", "web.site"]

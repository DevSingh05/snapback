"""Public data, item 6: Google Lens via SerpApi, the fallback when CoStar has no scan.
No network: answers are recordings in fixtures/public/recorded.json. The key here is fake."""

import logging

from snapback.agent.join import KitLookups
from snapback.contracts import (
    CardTone,
    DataSource,
    ForSaleStatus,
    ModuleEvidence,
    VerdictState,
)
from snapback.public import lens
from snapback.public.fetch import LiveFetcher, RecordedFetcher
from snapback.verdict import build_card, decide, to_evidence

KEY = "fake-test-key-123"
HIT = "House for rent https://images.example.test/ad/house-1.jpg call 555-0100"
RENT = "House https://images.example.test/ad/house-2.jpg"
NONE = "House https://images.example.test/ad/house-3.jpg"


class Spy:
    source = DataSource.FIXTURE

    def __init__(self):
        self.urls, self.timeouts = [], []

    def get(self, kind, key, url, timeout):
        self.urls.append(url)
        self.timeouts.append(timeout)
        return RecordedFetcher().get(kind, key, url, timeout)


def test_only_the_ads_own_photo_links_are_read_two_at_most():
    text = (
        "a https://images.example.test/ad/house-1.jpg b https://images.example.test/ad/house-1.jpg"
        " c https://x.example.test/p/2.PNG d https://x.example.test/p/3.webp"
    )
    assert lens.photo_urls(text) == [
        "https://images.example.test/ad/house-1.jpg",
        "https://x.example.test/p/2.PNG",
    ]
    assert lens.photo_urls("no photos, just https://example.test/page") == []


def test_a_photo_on_a_for_sale_page_is_a_for_sale_match_named_for_its_source():
    found = lens.check(HIT, RecordedFetcher(), KEY)
    assert found is not None and found.status is ForSaleStatus.ACTIVE
    assert (found.site, found.source_name) == ("zillow.com", "Google Lens via SerpApi")


def test_a_rental_page_or_no_match_is_nothing_found():
    assert lens.check(RENT, RecordedFetcher(), KEY) is None
    assert lens.check(NONE, RecordedFetcher(), KEY) is None


def test_no_key_no_photo_or_a_failure_is_not_checked():
    assert lens.check(HIT, RecordedFetcher(), None) is None
    assert lens.check("no photo here", RecordedFetcher(), KEY) is None

    class Down:
        source = DataSource.LIVE

        def get(self, kind, key, url, timeout):
            return None

    assert lens.check(HIT, Down(), KEY) is None


def test_the_request_is_google_lens_with_the_key_param_and_a_four_second_limit():
    spy = Spy()
    lens.check(HIT, spy, KEY, timeout=4.0)
    assert len(spy.urls) == 1 and spy.timeouts == [4.0]
    url = spy.urls[0]
    assert url.startswith("https://serpapi.com/search.json?engine=google_lens&url=")
    assert "https%3A%2F%2Fimages.example.test%2Fad%2Fhouse-1.jpg" in url
    assert url.endswith(f"&api_key={KEY}")


def test_at_most_two_searches_per_case():
    spy = Spy()
    text = " ".join(f"https://images.example.test/ad/house-{n}.jpg" for n in (1, 2, 3))
    lens.check(text, spy, KEY)
    assert len(spy.urls) == 2


def test_the_key_is_in_no_result_and_no_log(caplog):
    found = lens.check(HIT, RecordedFetcher(), KEY)
    assert KEY not in found.model_dump_json()
    with caplog.at_level(logging.DEBUG):
        dead = f"http://127.0.0.1:9/search.json?api_key={KEY}"
        assert LiveFetcher().get("lens", "k", dead, 0.2) is None
    assert KEY not in caplog.text


def test_a_fixture_run_and_a_live_run_without_a_key_look_nothing_up(monkeypatch):
    from snapback.settings import get_settings

    assert KitLookups(DataSource.FIXTURE).lens_for_sale(HIT) is None
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert KitLookups(DataSource.LIVE).lens_for_sale(HIT) is None
    finally:
        get_settings.cache_clear()


def test_the_match_holds_the_case_and_the_card_names_the_source():
    found = lens.check(HIT, RecordedFetcher(), KEY)
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, for_sale=found)
    assert decide(to_evidence(modules)).state is VerdictState.HOLD
    card = build_card(modules)
    (line,) = [ln for row in card.rows for ln in row.lines if ln.key == "label.for_sale"]
    assert line.tone is CardTone.HOLD and line.source_name == "Google Lens via SerpApi"


def test_a_live_run_with_a_key_searches_and_the_flag_turns_it_off(monkeypatch):
    from snapback.public import fetch
    from snapback.settings import get_settings

    monkeypatch.setenv("SERPAPI_API_KEY", KEY)
    monkeypatch.setattr(fetch, "fetcher_for", lambda source: RecordedFetcher())
    get_settings.cache_clear()
    try:
        found = KitLookups(DataSource.LIVE).lens_for_sale(HIT)
        assert found is not None and found.source_name == "Google Lens via SerpApi"
        monkeypatch.setenv("SNAPBACK_LENS", "false")
        get_settings.cache_clear()
        assert KitLookups(DataSource.LIVE).lens_for_sale(HIT) is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

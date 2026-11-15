"""Texas public records: Comptroller company check, HUD manager record, Houston address points.

Recorded responses in fixtures/tx_records/ (synthetic, 555 phones). No test calls the network:
every lookup takes the fetcher as an argument."""

import json
from pathlib import Path

import pytest

from snapback.adapters import tx_records
from snapback.contracts import DataSource, ModuleEvidence

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "tx_records"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fetcher(**by_host):
    """A fake GET: answers by which registry the URL belongs to; records what was asked."""
    asked = []

    def get(url, params):
        asked.append((url, dict(params)))
        for host, answer in by_host.items():
            if host in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected call {url}")

    get.asked = asked
    return get


AD = (
    "2 bed at 100 Fixture Lane, Houston TX 77000. Managed by Fixture Property Management. "
    "Call 713-555-0199 to see it."
)


# --- 1. Comptroller ---------------------------------------------------------------------


def test_an_active_company_reads_active_since_its_charter_year():
    get = fetcher(**{"data.texas.gov": _load("comptroller_active.json")})
    line = tx_records.comptroller_line("Fixture Property Management", get)
    assert (line.key, line.year, line.source) == (
        "comptroller_active",
        1994,
        "Texas Comptroller",
    )
    assert line.company == "Fixture Property Management"
    url, params = get.asked[0]
    assert "9cir-efmm" in url
    assert "FIXTURE PROPERTY" in params["$where"]


def test_a_company_that_is_not_listed_says_sole_proprietors_are_not_listed():
    get = fetcher(**{"data.texas.gov": _load("empty_list.json")})
    line = tx_records.comptroller_line("Nobody Rentals", get)
    assert line.key == "comptroller_none"


def test_a_listed_company_that_is_not_active_is_not_called_active():
    get = fetcher(**{"data.texas.gov": _load("comptroller_inactive.json")})
    line = tx_records.comptroller_line("Sample Realty Group", get)
    assert line.key == "comptroller_inactive"


def test_a_row_for_a_different_company_is_not_a_match():
    # "Fixture Living" shares only a later word with "Living Fixture Property": no match
    get = fetcher(**{"data.texas.gov": _load("comptroller_active.json")})
    line = tx_records.comptroller_line("Property Holdings", get)
    assert line.key == "comptroller_none"


def test_a_quote_in_the_company_name_cannot_break_the_query():
    get = fetcher(**{"data.texas.gov": []})
    tx_records.comptroller_line("O'Brien'; DROP TABLE x -- Rentals", get)
    where = get.asked[0][1]["$where"]
    assert "DROP" not in where and ";" not in where and "--" not in where


def test_no_company_in_the_ad_means_no_lookup():
    get = fetcher()
    assert tx_records.comptroller_line(None, get) is None
    assert get.asked == []


def test_a_failed_comptroller_call_is_not_checked_not_none():
    get = fetcher(**{"data.texas.gov": TimeoutError()})
    assert tx_records.comptroller_line("Fixture Property Management", get) is None


# --- 2. HUD manager ---------------------------------------------------------------------


def test_a_hud_building_names_its_manager():
    get = fetcher(**{"arcgis.com/VTyQ9soqVukalItT": _load("hud_multifamily.json")})
    lines = tx_records.hud_lines(AD, ["7135550199"], get)
    assert [line.key for line in lines] == ["hud_manager", "hud_phone_differs"]
    assert lines[0].company == "Fixture Residential LLC"
    assert all(line.source == "HUD" for line in lines)
    where = get.asked[0][1]["where"]
    assert "STD_ST='TX'" in where and "100" in where


def test_an_ad_phone_that_is_huds_number_gives_no_mismatch_line():
    get = fetcher(**{"arcgis.com/VTyQ9soqVukalItT": _load("hud_multifamily.json")})
    for number in ("7135550142", "7135550143"):  # the main line, the on-site line
        lines = tx_records.hud_lines(AD, [number], get)
        assert [line.key for line in lines] == ["hud_manager"]


def test_an_ad_with_no_phone_gets_the_manager_line_only():
    get = fetcher(**{"arcgis.com/VTyQ9soqVukalItT": _load("hud_multifamily.json")})
    assert [line.key for line in tx_records.hud_lines(AD, [], get)] == ["hud_manager"]


def test_a_street_that_is_not_on_huds_list_gives_nothing():
    other = _load("hud_multifamily.json")
    other["features"][0]["attributes"]["STD_ADDR"] = "900 Other St"
    get = fetcher(**{"arcgis.com/VTyQ9soqVukalItT": other})
    assert tx_records.hud_lines(AD, ["7135550199"], get) == []


def test_no_street_in_the_ad_means_no_lookup():
    get = fetcher()
    assert tx_records.hud_lines("Nice place, call me", [], get) == []
    assert get.asked == []


def test_no_phone_digits_are_kept_on_a_hud_line():
    get = fetcher(**{"arcgis.com/VTyQ9soqVukalItT": _load("hud_multifamily.json")})
    dump = json.dumps(
        [line.model_dump(mode="json") for line in tx_records.hud_lines(AD, ["7135550199"], get)]
    )
    for digits in ("5550142", "5550143", "5550199"):
        assert digits not in dump


# --- 3. Houston address points ---------------------------------------------------------


def test_an_exact_address_point_reports_its_zip():
    get = fetcher(**{"NummVBqZSIJKUeVR": _load("houston_site_address.json")})
    line = tx_records.address_point_line(AD, get)
    assert (line.key, line.zip_code, line.source) == (
        "address_point",
        "77000",
        "City of Houston",
    )
    assert get.asked[0][1]["where"] == "fulladdr='100 FIXTURE LN'"


def test_no_address_point_found_is_no_line():
    get = fetcher(**{"NummVBqZSIJKUeVR": _load("empty_features.json")})
    assert tx_records.address_point_line(AD, get) is None


# --- all together ----------------------------------------------------------------------


def _all():
    return fetcher(
        **{
            "data.texas.gov": _load("comptroller_active.json"),
            "VTyQ9soqVukalItT": _load("hud_multifamily.json"),
            "NummVBqZSIJKUeVR": _load("houston_site_address.json"),
        }
    )


def test_lookup_returns_every_line_labelled_with_its_data_source():
    lines = tx_records.lookup(AD, DataSource.LIVE, get=_all())
    assert {line.key for line in lines} == {
        "comptroller_active",
        "hud_manager",
        "hud_phone_differs",
        "address_point",
    }
    assert {line.data_source for line in lines} == {DataSource.LIVE}
    ModuleEvidence(case_id="x", source=DataSource.LIVE, public_records=lines)


def test_the_census_geocoder_hit_skips_the_address_point_fallback():
    lines = tx_records.lookup(AD, DataSource.LIVE, get=_all(), geocoder_hit=True)
    assert "address_point" not in {line.key for line in lines}


def test_one_registry_failing_leaves_the_others():
    get = fetcher(
        **{
            "data.texas.gov": TimeoutError(),
            "VTyQ9soqVukalItT": _load("hud_multifamily.json"),
            "NummVBqZSIJKUeVR": OSError(),
        }
    )
    keys = {line.key for line in tx_records.lookup(AD, DataSource.LIVE, get=get)}
    assert keys == {"hud_manager", "hud_phone_differs"}


def test_the_live_entry_point_does_nothing_unless_flag_and_live(monkeypatch):
    from snapback.settings import get_settings

    calls = []
    monkeypatch.setattr(tx_records, "_http_get_json", lambda *a, **k: calls.append(a) or [])
    for flag, source in ((False, DataSource.LIVE), (True, DataSource.FIXTURE)):
        monkeypatch.setattr(get_settings(), "snapback_tx_records", flag)
        assert tx_records.public_records(AD, source) == []
    assert calls == []


def test_the_http_get_has_a_three_second_deadline():
    assert tx_records.TIMEOUT_S == 3.0


# --- the card ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "es"])
def test_every_line_has_words_a_source_and_no_dashes(lang):
    from snapback.card import strings

    for key in (
        "comptroller_active",
        "comptroller_inactive",
        "comptroller_none",
        "hud_manager",
        "hud_phone_differs",
        "address_point",
    ):
        words = strings.text(f"records.{key}", lang, company="Acme", year=1994, zip_code="77000")
        assert words and "—" not in words and "–" not in words
    for label in ("label.src_comptroller", "label.src_hud", "label.src_houston"):
        assert strings.text(label, lang)


# --- on the card, and in the verdict ----------------------------------------------------

from datetime import datetime  # noqa: E402

from snapback.contracts import CardRowKind, CardTone  # noqa: E402
from snapback.verdict import build_card, decide, to_evidence  # noqa: E402

CHECKED_AT = datetime.fromisoformat("2026-11-14T10:00:00-05:00")


def _base():
    return ModuleEvidence.model_validate_json(
        (FIX.parent / "contracts" / "module_evidence_hold.json").read_text()
    )


def _with_records():
    lines = tx_records.lookup(AD, DataSource.LIVE, get=_all())
    return _base().model_copy(update={"public_records": lines})


def _card(modules, lang="en"):
    verdict = decide(to_evidence(modules, lang), lang)
    return verdict, build_card(modules, checked_at=CHECKED_AT, lang=lang)


def test_the_card_shows_each_line_under_its_source_and_changes_no_verdict():
    plain_verdict, plain = _card(_base())
    verdict, card = _card(_with_records())
    assert verdict == plain_verdict  # nothing here reaches decide()
    assert card.state == plain.state
    assert card.summary == plain.summary
    by_row = {row.kind: row for row in card.rows}
    person = {line.label: line.text for line in by_row[CardRowKind.PERSON].lines}
    assert person["Texas Comptroller"] == (
        "Texas Comptroller: Fixture Property Management is an active Texas company since 1994."
    )
    assert person["HUD record"] in (
        "HUD's record lists the manager as Fixture Residential LLC.",
        "The ad's phone isn't the manager's number on HUD's record.",
    )
    texts = [line.text for line in by_row[CardRowKind.PERSON].lines]
    assert "The ad's phone isn't the manager's number on HUD's record." in texts
    assert any("ZIP 77000" in line.text for line in by_row[CardRowKind.PLACE].lines)
    new = [
        line
        for row in card.rows
        for line in row.lines
        if line.label in ("Texas Comptroller", "HUD record", "City of Houston")
    ]
    assert len(new) == 4
    assert {line.tone for line in new} == {CardTone.NOT_CHECKED}
    assert {line.source for line in new} == {DataSource.LIVE}


def test_the_spanish_card_has_the_same_lines():
    _, card = _card(_with_records(), "es")
    labels = {line.label for row in card.rows for line in row.lines}
    assert {"Contralor de Texas", "Registro de HUD", "Ciudad de Houston"} <= labels


def test_no_public_records_leaves_the_card_as_it_was():
    base = _base()
    _, card = _card(base)
    assert not {"Texas Comptroller", "HUD record", "City of Houston"} & {
        line.label for row in card.rows for line in row.lines
    }


def test_the_plan_carries_public_records_into_the_evidence():
    from snapback.agent import FixtureModules
    from snapback.agent.planner import Plan, PlanKind

    lines = tx_records.lookup(AD, DataSource.LIVE, get=_all())

    class Modules(FixtureModules):
        def public_records(self, case_id):
            return lines

    plan = Plan(Modules(), "fx-1")
    assert plan._skip_reason(PlanKind.CLAIMS) is None
    assert plan.run(PlanKind.CLAIMS)["public_records"] == lines


def test_a_plan_with_no_public_records_and_no_notes_skips_the_option():
    from snapback.agent import FixtureModules
    from snapback.agent.planner import Plan, PlanKind

    plan = Plan(FixtureModules(), "fx-1")
    assert plan._skip_reason(PlanKind.CLAIMS) == "plan.skip.claims_none"
    assert PlanKind.CLAIMS not in plan.open_options()

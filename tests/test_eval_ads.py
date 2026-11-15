"""`make eval-ads`: the composed ads are deterministic, each type has its expected verdict,
the CSV has the agreed schema, and the route serves it."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from snapback.api.eval_results import ADS_COLUMNS
from snapback.api.main import create_app
from snapback.contracts import DataSource, VerdictState
from snapback.eval import ads
from snapback.settings import Settings

TYPES = {ads.CLONE_PHONE, ads.OTHER_PHOTOS, ads.PRICE_CUT, ads.FOR_SALE, ads.CLEAN}


@pytest.fixture(scope="module")
def result() -> ads.Run:
    return ads.run(DataSource.FIXTURE)


def test_composition_is_deterministic():
    first = ads.compose(DataSource.FIXTURE) + ads.compose_messages(DataSource.FIXTURE)
    second = ads.compose(DataSource.FIXTURE) + ads.compose_messages(DataSource.FIXTURE)
    assert [(a.ad_id, a.text) for a in first] == [(a.ad_id, a.text) for a in second]


def test_every_composed_type_is_present_and_all_labelled_messages_run(result):
    kinds = {a.ad_type for a in result.ads}
    assert kinds >= TYPES
    cases = json.loads(ads.CASES_FILE.read_text())
    assert len(cases) >= 49
    assert len([a for a in result.ads if a.ad_type.startswith("labelled_message")]) == len(cases)
    message_ids = {a.ad_id for a in result.ads if a.ad_type.startswith("labelled_message")}
    assert message_ids == {c["id"] for c in cases}


def test_each_composed_type_gets_its_expected_verdict(result):
    for ad in result.ads:
        if ad.ad_type in TYPES:
            assert result.verdicts[ad.ad_id] == ads.EXPECTED[ad.ad_type], ad.ad_id


def test_expected_verdicts_are_fixed_per_type_and_distinct_where_the_policy_is():
    assert ads.EXPECTED[ads.OTHER_PHOTOS] is VerdictState.DONT_PAY
    assert ads.EXPECTED[ads.CLEAN] is VerdictState.VERIFIED
    assert ads.EXPECTED[ads.CLONE_PHONE] is VerdictState.HOLD
    assert set(ads.EXPECTED) == set(ads.ORIGIN)


def test_a_changed_phone_is_what_flips_the_clean_ad(result):
    clean = next(a for a in result.ads if a.ad_type == ads.CLEAN)
    other = clean.__class__(
        "probe",
        ads.CLONE_PHONE,
        clean.text.replace(clean.building.office_phone, "(555) 010-9999"),
        clean.building,
    )
    assert result.verdicts[clean.ad_id] is VerdictState.VERIFIED
    assert ads.run_ad(other) is VerdictState.HOLD


def test_csv_schema_and_counts(result, tmp_path):
    out = tmp_path / "ads.csv"
    ads.write(result, out)
    text = out.read_text()
    lines = text.splitlines()
    assert lines[0].startswith("# FIXTURE")
    assert any("composed" in line for line in lines if line.startswith("#"))
    body = list(csv.reader(io.StringIO("\n".join(x for x in lines if not x.startswith("#")))))
    assert tuple(body[0]) == ADS_COLUMNS
    rows = [dict(zip(ADS_COLUMNS, r, strict=True)) for r in body[1:]]
    total = next(r for r in rows if r["ad_type"] == "all" and r["got"] == "(as expected)")
    assert int(total["n"]) == len(result.ads)
    missed = next(r for r in rows if r["ad_type"] == "all" and r["got"] == "(missed)")
    assert int(total["k"]) + int(missed["k"]) == len(result.ads)
    for r in rows:
        assert 0 <= float(r["ci_low"]) <= float(r["rate"]) <= float(r["ci_high"]) <= 1
        assert r["miss"] in ("0", "1") and r["frozen_at"] == "FIXTURE"
        assert (r["miss"] == "1") == (r["got"] not in (r["expected"], "(as expected)"))
    # No ad text, address or phone digits in the file.
    assert "555" not in text and "Fixture Way" not in text


def test_the_route_serves_the_written_file(result, tmp_path):
    out = tmp_path / "eval" / "ads_results.csv"
    ads.write(result, out)
    client = TestClient(
        create_app(Settings(_env_file=None, snapback_data_dir=tmp_path, snapback_eval_ads=out))
    )
    response = client.get("/eval/ads.csv")
    assert response.status_code == 200 and response.content == out.read_bytes()
    out.write_text("a,b\n1,2\n")
    assert client.get("/eval/ads.csv").status_code == 500
    out.unlink()
    assert client.get("/eval/ads.csv").status_code == 404

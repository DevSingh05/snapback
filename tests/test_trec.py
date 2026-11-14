"""D10 #128: TREC license lookup. Synthetic fx- names, HTTP mocked, no network."""

import time

import httpx

from snapback.adapters.trec import check_license, detect_claim
from snapback.contracts import LicenseResult, LicenseStatus


def _row(status: str, sponsor_type: str = "Broker Company", sponsor: str = "Fx Realty Group"):
    return {
        "license_type": "Sales Agent",
        "license_number": "000000",
        "full_name": "Fxperson, Fxname",
        "first_name": "FXNAME",
        "last_name": "FXPERSON",
        "status": status,
        "related_license_type": sponsor_type,
        "related_license_full_name": sponsor,
    }


def _client(rows=None, *, status=200, fail=False, seen=None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if fail:
            raise httpx.ConnectTimeout("fx timeout")
        return httpx.Response(status, json=rows or [])

    return httpx.Client(transport=httpx.MockTransport(handler))


CLAIM = "Hi, I'm Fxname Fxperson, a licensed realtor. Zelle the deposit to hold it."


def _check(text: str, client: httpx.Client, tmp_path) -> LicenseResult:
    return check_license(text, client=client, cache_dir=tmp_path)


def test_claimed_and_no_license_is_not_found(tmp_path):
    result = _check(CLAIM, _client([]), tmp_path)
    assert result.status is LicenseStatus.NOT_FOUND
    assert result.claimed_role == "agent"


def test_claimed_and_active_is_licensed_with_the_company_broker(tmp_path):
    result = _check(CLAIM, _client([_row("Active")]), tmp_path)
    assert result.status is LicenseStatus.LICENSED
    assert result.sponsor_broker == "Fx Realty Group"


def test_claimed_and_inactive_is_not_found(tmp_path):
    for status in ("Inactive", "Expired less than 6 months", "Revoked", "Probation - Inactive"):
        result = _check(CLAIM, _client([_row(status)]), tmp_path)
        assert result.status is LicenseStatus.NOT_FOUND, status


def test_an_active_variant_counts_as_active(tmp_path):
    result = _check(CLAIM, _client([_row("Probation - Active")]), tmp_path)
    assert result.status is LicenseStatus.LICENSED


def test_an_individual_sponsor_is_never_named(tmp_path):
    rows = [_row("Active", sponsor_type="Broker Individual", sponsor="Fxbroker, Fxperson")]
    result = _check(CLAIM, _client(rows), tmp_path)
    assert result.status is LicenseStatus.LICENSED and result.sponsor_broker is None


def test_no_claim_is_not_checked_and_makes_no_call(tmp_path):
    seen: list = []
    text = "I'm the owner, renting my own home while I work abroad."
    result = _check(text, _client([], seen=seen), tmp_path)
    assert result.status is LicenseStatus.NOT_CHECKED
    assert seen == []


def test_a_claim_with_no_name_is_not_checked(tmp_path):
    result = _check("I am a licensed agent for this property.", _client([]), tmp_path)
    assert result.status is LicenseStatus.NOT_CHECKED and result.claimed_role == "agent"


def test_a_timeout_or_error_is_not_checked(tmp_path):
    assert _check(CLAIM, _client(fail=True), tmp_path).status is LicenseStatus.NOT_CHECKED
    assert _check(CLAIM, _client(status=500), tmp_path).status is LicenseStatus.NOT_CHECKED
    assert _check(CLAIM, _client(status=429), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_the_result_never_keeps_a_person_or_a_license_number(tmp_path):
    result = _check(CLAIM, _client([_row("Active")]), tmp_path)
    text = result.model_dump_json().lower()
    assert "fxname" not in text and "fxperson" not in text and "000000" not in text


def test_the_query_asks_for_the_claimed_name_only(tmp_path):
    seen: list = []
    _check(CLAIM, _client([], seen=seen), tmp_path)
    where = seen[0].url.params["$where"]
    assert "FXNAME" in where and "FXPERSON" in where
    assert seen[0].url.host == "data.texas.gov"


def test_answers_are_cached_locally(tmp_path):
    seen: list = []
    client = _client([_row("Active")], seen=seen)
    _check(CLAIM, client, tmp_path)
    again = _check(CLAIM, client, tmp_path)
    assert again.status is LicenseStatus.LICENSED and len(seen) == 1
    assert not any("fxname" in p.name.lower() for p in tmp_path.rglob("*"))  # names hashed


def test_a_long_text_does_not_slow_the_claim_detector():
    text = ("realtor " * 50_000) + "a" * 500_000
    start = time.perf_counter()
    detect_claim(text)
    assert time.perf_counter() - start < 0.5


def test_claim_roles_and_names():
    assert detect_claim("I'm a locator, call me. - Fxname Fxperson").role == "locator"
    assert detect_claim("Broker: Fxname Fxperson").role == "broker"
    found = detect_claim("My name is Fxname Fxperson and I am a real estate agent.")
    assert (found.role, found.first, found.last) == ("agent", "Fxname", "Fxperson")
    assert detect_claim("Lovely 2 bed, the agent fee is waived.") is None  # no self-claim

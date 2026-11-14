"""D10 #128: TREC license lookup. Synthetic fx- names, HTTP mocked, no network."""

import re
import time

import httpx

from snapback.adapters.trec import check_license, detect_claim
from snapback.contracts import LicenseResult, LicenseStatus


def _row(
    status: str,
    sponsor_type: str = "Broker Company",
    sponsor: str = "Fx Realty Group",
    first: str = "FXNAME",
    middle: str = "",
    last: str = "FXPERSON",
):
    return {
        "license_type": "Sales Agent",
        "license_number": "000000",
        "full_name": f"{last.title()}, {first.title()}",
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "status": status,
        "related_license_type": sponsor_type,
        "related_license_full_name": sponsor,
    }


def _matches_where(row: dict, where: str) -> bool:
    """Apply the parts of the SoQL filter the adapter sends, so the mock cannot hide a bad query."""
    last = re.search(r"upper\(last_name\)='([^']*)'", where)
    if last and str(row.get("last_name", "")).upper() != last.group(1):
        return False
    first = re.search(r"upper\(first_name\)='([^']*)'", where)
    if first and str(row.get("first_name", "")).upper() != first.group(1):
        return False
    ends = re.search(r"upper\(last_name\) like '% ([^']*)'", where)
    if ends and not str(row.get("last_name", "")).upper().endswith(" " + ends.group(1)):
        return False
    kind = re.search(r"license_type='([^']*)'", where)
    if kind and row.get("license_type") != kind.group(1):
        return False
    like = re.search(r"upper\(full_name\) like '([^']*)%'", where)
    return not like or str(row.get("full_name", "")).upper().startswith(like.group(1))


def _client(rows=None, *, status=200, fail=False, seen=None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if fail:
            raise httpx.ConnectTimeout("fx timeout")
        where = request.url.params.get("$where", "")
        limit = int(request.url.params.get("$limit", "1000"))
        kept = [row for row in (rows or []) if _matches_where(row, where)][:limit]
        return httpx.Response(status, json=kept)

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


def test_the_query_asks_by_last_name_only(tmp_path):
    seen: list = []
    _check(CLAIM, _client([], seen=seen), tmp_path)
    where = seen[0].url.params["$where"]
    assert "FXPERSON" in where and "FXNAME" not in where
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


def test_a_nickname_counts_as_licensed(tmp_path):
    text = "Hi, I'm Mike Fxperson, a licensed realtor."
    rows = [_row("Active", first="MICHAEL")]
    assert _check(text, _client(rows), tmp_path).status is LicenseStatus.LICENSED


def test_an_initial_or_a_middle_name_counts(tmp_path):
    initial = _check(
        "J. Fxperson here? No: I'm Jay Fxperson, a licensed realtor.",
        _client([_row("Active", first="JAMES", middle="JAY")]),
        tmp_path,
    )
    assert initial.status is LicenseStatus.LICENSED  # goes by the middle name


def test_an_active_namesake_with_another_first_name_is_not_checked(tmp_path):
    # ruling 02:50: anyone active sharing the last name means we cannot say "not found"
    rows = [_row("Active", first="ZORA"), _row("Active", first="QUINN")]
    assert _check(CLAIM, _client(rows), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_only_inactive_matches_and_no_active_namesake_is_not_found(tmp_path):
    rows = [_row("Expired more than 6 months"), _row("Inactive", first="ZORA")]
    assert _check(CLAIM, _client(rows), tmp_path).status is LicenseStatus.NOT_FOUND
    with_active = [_row("Expired more than 6 months"), _row("Active", first="ZORA")]
    assert _check(CLAIM, _client(with_active), tmp_path / "b").status is LicenseStatus.NOT_CHECKED


def test_more_than_25_rows_is_not_checked(tmp_path):
    rows = [_row("Active", first=f"FX{i:02d}") for i in range(26)]
    assert _check(CLAIM, _client(rows), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_several_compatible_people_are_licensed_with_no_sponsor_named(tmp_path):
    text = "I'm Chris Fxperson, a licensed realtor."
    rows = [
        _row("Active", first="CHRISTOPHER", sponsor="Fx One Realty"),
        _row("Active", first="CHRISTINA", sponsor="Fx Two Realty"),
    ]
    result = _check(text, _client(rows), tmp_path)
    assert result.status is LicenseStatus.LICENSED and result.sponsor_broker is None


def test_a_named_brokerage_is_checked_as_a_company(tmp_path):
    seen: list = []
    text = "Listed by Fxample Realty Group. Deposit by Zelle today."
    company = {
        "license_type": "Broker Company",
        "full_name": "FXAMPLE REALTY GROUP, LLC",
        "status": "Active",
    }
    result = _check(text, _client([company], seen=seen), tmp_path)
    assert result.status is LicenseStatus.LICENSED and result.claimed_role == "company"
    assert "Broker Company" in seen[0].url.params["$where"]
    missing = _check("Managed by Fxnone Properties.", _client([]), tmp_path)
    assert missing.status is LicenseStatus.NOT_FOUND


class _Trickle(httpx.SyncByteStream):
    def __init__(self, now: list[float], body: bytes, step: float) -> None:
        self.now, self.body, self.step = now, body, step

    def __iter__(self):
        for i in range(0, len(self.body), 4):
            self.now[0] += self.step
            yield self.body[i : i + 4]


def test_the_5_s_budget_covers_the_whole_call(tmp_path, monkeypatch):
    from snapback.adapters import trec

    now = [0.0]
    monkeypatch.setattr(trec, "_monotonic", lambda: now[0])
    body = b"[]" + b" " * 200  # a slow server: 4 bytes a second

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_Trickle(now, body, 1.0))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check(CLAIM, client, tmp_path).status is LicenseStatus.NOT_CHECKED
    assert now[0] <= 6.0


def test_labels_are_not_read_as_names(tmp_path):
    seen: list = []
    for text in (
        "Contact our Licensed Real Estate Agent today.",
        "Free Apartment Locator service, no fees!",
        "Use Our Apartment Locator to find more.",
        "Please Contact your agent for a tour.",
    ):
        result = _check(text, _client([], seen=seen), tmp_path)
        assert result.status is LicenseStatus.NOT_CHECKED, text
    assert seen == []  # no lookup was made for any of them


def test_a_signature_wins_over_a_bare_im(tmp_path):
    seen: list = []
    text = "I'm Very Excited to show it! I am a licensed agent. - Fxname Fxperson"
    _check(text, _client([], seen=seen), tmp_path)
    assert "FXPERSON" in seen[0].url.params["$where"]
    found = detect_claim(text)
    assert (found.first, found.last) == ("Fxname", "Fxperson")


def test_an_owner_who_claims_a_license_is_checked(tmp_path):
    loose = "I'm the owner and also a licensed broker. - Fxname Fxperson"
    assert detect_claim(loose).role == "broker"
    # a loose claim is looked up but can never be NOT_FOUND
    assert _check(loose, _client([]), tmp_path).status is LicenseStatus.NOT_CHECKED
    strict = "I'm Fxname Fxperson, a licensed broker, and also the owner."
    assert _check(strict, _client([]), tmp_path / "b").status is LicenseStatus.NOT_FOUND


def test_a_read_only_cache_still_returns_the_answer(tmp_path, monkeypatch):
    from pathlib import Path

    def refuse(self, *args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "write_text", refuse)
    result = _check(CLAIM, _client([_row("Active")]), tmp_path)
    assert result.status is LicenseStatus.LICENSED


def test_a_brokerage_name_is_never_read_as_a_person(tmp_path):
    seen: list = []
    for text in (
        "Broker: Fxbeta Realty LLC",
        "Call us today. - Fxbeta Realty",
        "Fxjane Fxdoe | Fxbeta Realty, Realtor",
    ):
        _check(text, _client([], seen=seen), tmp_path)
    assert not any(
        "REALTY" in r.url.params.get("$where", "") and "last_name" in r.url.params.get("$where", "")
        for r in seen
    )


def test_compound_surnames_never_end_not_found(tmp_path):
    assert (
        _check("My name is Fxana De La Fxcruz, a licensed agent.", _client([]), tmp_path).status
        is LicenseStatus.NOT_CHECKED
    )
    assert (
        _check(
            "My name is Fxana Fxgarcia Fxlopez, a licensed agent.", _client([]), tmp_path / "b"
        ).status
        is LicenseStatus.NOT_CHECKED
    )
    # "Fxcruz" claimed, but an active "DE LA FXCRUZ" exists: the like-query catches it
    rows = [_row("Active", first="FXANA", last="DE LA FXCRUZ")]
    strict = "I'm Fxana Fxcruz, a licensed agent."
    assert _check(strict, _client(rows), tmp_path / "c").status is LicenseStatus.NOT_CHECKED


def test_a_role_word_needs_a_separator_or_an_article():
    for text in ("Email Listing Agent for a tour", "Landlord Pays Broker Fee", "Rent Fast Locator"):
        assert detect_claim(text) is None, text


def test_no_signature_and_a_slogan_intro_is_not_checked(tmp_path):
    text = "I'm Very Excited to help, licensed agent"
    assert _check(text, _client([]), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_the_signature_wins_over_an_im_name(tmp_path):
    seen: list = []
    text = "I'm Fxsunny Fxday here to help! I am a licensed agent. - Fxname Fxperson"
    _check(text, _client([], seen=seen), tmp_path)
    assert (
        "FXPERSON" in seen[0].url.params["$where"] and "FXDAY" not in seen[0].url.params["$where"]
    )


def test_slow_headers_are_bounded_by_the_deadline(tmp_path, monkeypatch):
    from snapback.adapters import trec

    monkeypatch.setattr(trec, "TIMEOUT_S", 0.3)

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(1.5)  # nothing at all for 1.5 s
        return httpx.Response(200, json=[])

    start = time.perf_counter()
    result = _check(CLAIM, httpx.Client(transport=httpx.MockTransport(handler)), tmp_path)
    assert result.status is LicenseStatus.NOT_CHECKED
    assert time.perf_counter() - start < 1.0


def test_a_not_found_answer_expires_after_24_hours(tmp_path, monkeypatch):
    seen: list = []
    client = _client([], seen=seen)
    assert _check(CLAIM, client, tmp_path).status is LicenseStatus.NOT_FOUND
    calls = len(seen)
    _check(CLAIM, client, tmp_path)
    assert len(seen) == calls  # cached
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 25 * 3600)
    _check(CLAIM, client, tmp_path)
    assert len(seen) > calls  # looked up again

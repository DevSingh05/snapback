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


def _cond_ok(row: dict, cond: str) -> bool:
    """One SoQL condition the adapter sends: `upper(f)='X'`, `upper(f) like 'P'` (any % pattern)
    or `f='X'`. An unknown shape fails loudly, so the mock cannot hide a bad query."""
    cond = cond.strip()
    m = re.fullmatch(r"upper\((\w+)\)\s*=\s*'(.*)'", cond)
    if m:
        return str(row.get(m.group(1)) or "").upper() == m.group(2).replace("''", "'")
    m = re.fullmatch(r"upper\((\w+)\)\s+like\s+'(.*)'", cond)
    if m:
        pattern = ".*".join(re.escape(p) for p in m.group(2).replace("''", "'").split("%"))
        return re.fullmatch(pattern, str(row.get(m.group(1)) or "").upper(), re.S) is not None
    m = re.fullmatch(r"(\w+)\s*=\s*'(.*)'", cond)
    if m:
        return str(row.get(m.group(1)) or "") == m.group(2)
    raise AssertionError(f"the mock cannot evaluate: {cond}")


def _matches_where(row: dict, where: str) -> bool:
    return all(_cond_ok(row, cond) for cond in where.split(" AND "))


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
    # a company is never NOT_FOUND, even when no brokerage starts with the name
    missing = _check("Managed by Fxnone Properties.", _client([]), tmp_path)
    assert missing.status is LicenseStatus.NOT_CHECKED


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
    for text in (
        "Email Listing Agent for a tour",
        "Landlord Pays Broker Fee",
        "Rent Fast Locator",
        "Fxzed Fxquick Agent for a tour",  # a name then a role word, no separator or article
    ):
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


def _licensees():
    return [
        _row("Active", first="FXTOM", last="FXKING JR"),  # suffix kept inside last_name
        _row("Active", first="FXMARIA", last="FXGARCIA FXLOPEZ"),  # two surnames, space
        _row("Active", first="FXLEE", last="FXNGUYEN-FXTRAN"),  # hyphen
        _row("Active", first="FXANA", last="FXRUIZ-FXVEGA"),
    ]


def test_a_surname_contained_in_an_active_last_name_is_never_not_found(tmp_path):
    cases = {
        "P1 suffix in last_name": "Fxtom Fxking, REALTOR\nFxbeta Realty LLC\nCell 555-0100",
        "P3 first of two surnames": "I'M FXMARIA FXGARCIA, A LICENSED REALTOR. TEXT 555-0100",
        "P4 hyphen against a space": "Hi, I'm Fxmaria Fxgarcia-Fxlopez, a licensed realtor.",
        "P7 second part of a hyphen": "Soy agente con licencia.\n- Fxana Fxvega, Realtor",
        "X1 hyphen part, intro": "Hi, I'm Fxlee Fxtran, a licensed realtor.",
        "X2 suffix, intro": "My name is Fxtom Fxking, a licensed agent.",
    }
    for i, (label, text) in enumerate(cases.items()):
        result = _check(text, _client(_licensees()), tmp_path / str(i))
        assert result.status is LicenseStatus.NOT_CHECKED, label


def test_every_part_of_a_surname_is_asked_with_contains(tmp_path):
    seen: list = []
    result = _check(
        "Hi, I'm Fxname Fxperson, a licensed realtor.", _client([], seen=seen), tmp_path
    )
    wheres = [r.url.params["$where"] for r in seen]
    assert result.status is LicenseStatus.NOT_FOUND
    assert "upper(last_name) like '%FXPERSON%'" in wheres


def test_a_hyphen_or_apostrophe_surname_is_never_strict(tmp_path):
    for i, text in enumerate(
        (
            "I'm Fxname Fxper-Fxson, a licensed realtor.",
            "I'm Fxname Fxo'Fxperson, a licensed agent.",
        )
    ):
        assert _check(text, _client([]), tmp_path / str(i)).status is LicenseStatus.NOT_CHECKED


def test_a_suffix_is_not_asked_and_over_25_contains_rows_is_not_checked(tmp_path):
    from snapback.adapters.trec import _surname_parts

    assert _surname_parts("Fxking Jr.") == ["FXKING"]
    assert _surname_parts("Fxo'Fxper-Fxson III") == ["FXO", "FXPER", "FXSON"]
    crowd = [_row("Inactive", first=f"FX{i:02d}", last=f"FXPERSON{i}") for i in range(26)]
    assert _check(CLAIM, _client(crowd), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_a_company_is_never_not_found(tmp_path):
    seen: list = []
    zero = _check("Listed by Fxnone Properties.", _client([], seen=seen), tmp_path)
    assert zero.status is LicenseStatus.NOT_CHECKED and len(seen) == 1
    dba = [{"license_type": "Broker Company", "full_name": "FXOTHER REALTY GROUP LLC",
            "status": "Active"}]  # fmt: skip
    near = _check("Listed by Fxother Realty.", _client(dba), tmp_path / "b")
    assert near.status is LicenseStatus.NOT_CHECKED


def test_the_slogan_intro_with_a_strict_shape_makes_no_lookup(tmp_path):
    seen: list = []
    text = "I'm Very Excited, a licensed agent here to help."
    result = _check(text, _client([], seen=seen), tmp_path)
    assert result.status is LicenseStatus.NOT_CHECKED
    assert seen == [] and detect_claim(text) is None


def test_a_sponsor_is_named_only_for_exactly_one_company(tmp_path):
    same = [_row("Active", sponsor="Fx One Realty"), _row("Active", sponsor="Fx One Realty")]
    assert _check(CLAIM, _client(same), tmp_path).sponsor_broker == "Fx One Realty"
    two = [_row("Active", sponsor="Fx One Realty"), _row("Active", sponsor="Fx Two Realty")]
    assert _check(CLAIM, _client(two), tmp_path / "b").sponsor_broker is None
    mixed_sponsors = [_row("Active", sponsor="Fx One Realty"), _row("Active", sponsor_type="X")]
    assert _check(CLAIM, _client(mixed_sponsors), tmp_path / "c").sponsor_broker == "Fx One Realty"


ROUND_2_SENTENCES = {
    "A": "Great 2 bed near campus. Broker: Fxbeta Realty LLC. Call Fxjane",
    "B": "I'm a licensed realtor with great rates. - Fxbeta Realty",
    "C": "Fxjane Fxdoe | Fxbeta Realty, Realtor.",
    "D": "I'm Fxmaria De La Fxcruz, a licensed realtor",
    "E": "Fxana Fxgarcia Fxlopez, licensed agent.",
    "F": "Listed by Fxbeta Realty\nSchedule A Tour Today",
    "G": "Listed by Fxacme Realty.",
    "H": "Showings: Email Listing Agent for a time.",
    "I": "Landlord Pays Broker Fee.",
}


def test_round_2_sentences_never_give_not_found(tmp_path):
    acme = {"license_type": "Broker Company", "full_name": "FXACME REALTY GROUP LLC",
            "status": "Active"}  # fmt: skip
    for key, text in ROUND_2_SENTENCES.items():
        for variant, rows in (("empty", []), ("acme", [acme])):
            result = _check(text, _client(rows), tmp_path / f"{key}{variant}")
            assert result.status is not LicenseStatus.NOT_FOUND, key

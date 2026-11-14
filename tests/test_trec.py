"""D10 #128: TREC license lookup. Synthetic fx- names, HTTP mocked, no network."""

import json
import re
import time

import httpx

from snapback.adapters.trec import check_license, detect_claim
from snapback.contracts import LicenseResult, LicenseStatus


def _row(
    status: str,
    number: str = "000000-SA",
    sponsor_type: str = "Broker Company",
    sponsor: str = "Fx Realty Group",
    first: str = "FXNAME",
    middle: str = "",
    last: str = "FXPERSON",
):
    return {
        "license_type": "Sales Agent",
        "license_number": number,
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


def test_claimed_and_no_license_is_only_not_checked(tmp_path):
    # ruling 04:24: no name lookup can rule a person out, so a name never gives NOT_FOUND
    result = _check(CLAIM, _client([]), tmp_path)
    assert result.status is LicenseStatus.NOT_CHECKED
    assert result.claimed_role == "agent"


def test_claimed_and_active_is_licensed_with_the_company_broker(tmp_path):
    result = _check(CLAIM, _client([_row("Active")]), tmp_path)
    assert result.status is LicenseStatus.LICENSED
    assert result.sponsor_broker == "Fx Realty Group"


def test_claimed_and_inactive_is_not_checked(tmp_path):
    for i, status in enumerate(
        ("Inactive", "Expired less than 6 months", "Revoked", "Probation - Inactive")
    ):
        result = _check(CLAIM, _client([_row(status)]), tmp_path / str(i))
        assert result.status is LicenseStatus.NOT_CHECKED, status


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


def test_only_inactive_matches_or_an_active_namesake_is_not_checked(tmp_path):
    rows = [_row("Expired more than 6 months"), _row("Inactive", first="ZORA")]
    assert _check(CLAIM, _client(rows), tmp_path).status is LicenseStatus.NOT_CHECKED
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
    # a loose claim is looked up and gives LICENSED or NOT_CHECKED
    assert _check(loose, _client([]), tmp_path).status is LicenseStatus.NOT_CHECKED
    strict = "I'm Fxname Fxperson, a licensed broker, and also the owner."
    assert _check(strict, _client([]), tmp_path / "b").status is LicenseStatus.NOT_CHECKED


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
    for i, text in enumerate(
        (
            "My name is Fxana De La Fxcruz, a licensed agent.",
            "My name is Fxana Fxgarcia Fxlopez, a licensed agent.",
        )
    ):
        assert _check(text, _client([]), tmp_path / str(i)).status is LicenseStatus.NOT_CHECKED
    # "Fxcruz" claimed and an active "DE LA FXCRUZ" exists: the full-name query finds them
    rows = [_row("Active", first="FXANA", last="DE LA FXCRUZ")]
    strict = "I'm Fxana Fxcruz, a licensed agent."
    assert _check(strict, _client(rows), tmp_path / "c").status is LicenseStatus.LICENSED


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


def _licensees():
    return [
        _row("Active", first="FXTOM", last="FXKING JR"),  # suffix kept inside last_name
        _row("Active", first="FXMARIA", last="FXGARCIA FXLOPEZ"),  # two surnames, space
        _row("Active", first="FXLEE", last="FXNGUYEN-FXTRAN"),  # hyphen
        _row("Active", first="FXANA", last="FXRUIZ-FXVEGA"),
    ]


def test_a_real_licensee_stored_in_another_shape_is_never_not_found(tmp_path):
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
        assert result.status is LicenseStatus.LICENSED, label


def _p(first, last, middle="", status="Active", lt="Sales Agent", number="000000-SA"):
    """A row in the live shape: full_name is 'FIRST MIDDLE LAST'."""
    row = _row(status, first=first, middle=middle, last=last, number=number)
    row["license_type"] = lt
    row["full_name"] = " ".join(x for x in (first, middle, last) if x)
    return row


ADV8 = [
    (
        "1 Lee inside Leeds",
        "Hi, I'm Fxjo Fxlee, a licensed realtor.",
        [_p(f"FXA{i}", "FXLEEDS") for i in range(3)] + [_p("FXJOANNA", "FXLEE JR")],
    ),
    (
        "2a family first, 2 tokens",
        "Xin chao! I'm Fxnguyen Fxan, a licensed realtor.",
        [_p("FXAN", "FXNGUYEN", middle="FXVAN")],
    ),
    (
        "2b 3 tokens",
        "I'm Fxnguyen Fxvan Fxan, a licensed realtor.",
        [_p("FXAN", "FXNGUYEN", middle="FXVAN")],
    ),
    ("2c Korean", "I'm Fxkim Fxminjun, a licensed agent.", [_p("FXMINJUN", "FXKIM")]),
    ("2d Chinese", "My name is Fxwang Fxxiuying, a licensed realtor.", [_p("FXXIUYING", "FXWANG")]),
    ("2e signature", "Nice 2/1 near Bellaire.\n- Fxzhang Fxwei, Realtor", [_p("FXWEI", "FXZHANG")]),
    ("3a Mc joined", "I'm Fxjane Mcfxcall, a licensed realtor.", [_p("FXJANE", "MC FXCALL")]),
    (
        "3b O' without apostrophe",
        "I'm Fxsean Ofxbrien, a licensed agent.",
        [_p("FXSEAN", "O'FXBRIEN")],
    ),
    (
        "3c O' with apostrophe",
        "I'm Fxsean O'Fxbrien, a licensed agent.",
        [_p("FXSEAN", "O'FXBRIEN")],
    ),
    (
        "4 nickname not in table",
        "Hi, I'm Fxbubba Fxdoe, a licensed realtor.",
        [_p("FXWALTER", "FXDOE")],
    ),
    (
        "5a maiden name as middle",
        "I'm Fxjane Fxsmith, a licensed agent.",
        [_p("FXJANE", "FXJONES", middle="FXSMITH")],
    ),
    ("5b married name", "I'm Fxjane Fxjones, a licensed agent.", [_p("FXJANE", "FXSMITH")]),
    (
        "5c paternal surname as middle",
        "Hola, I'm Fxmaria Fxgarcia, a licensed realtor.",
        [_p("FXMARIA", "FXLOPEZ", middle="FXGARCIA")],
    ),
    (
        "6a team signature",
        "Text us for a tour!\nThe Fxdoe Team | eXp Realty",
        [_p("FXJANE", "FXDOE")],
    ),
    (
        "6b name + team",
        "Fxjane Fxdoe, Realtor\nThe Fxdoe Team | eXp Realty",
        [_p("FXJANE", "FXDOE")],
    ),
    (
        "7a Broker/Owner signature",
        "Showings daily.\nFxjane Fxdoe, Broker/Owner\nFxbeta Realty",
        [_p("FXJANE", "FXDOE", lt="Broker")],
    ),
    (
        "7b Broker/Owner intro",
        "I'm Fxjane Fxdoe, Broker/Owner of Fxbeta Realty.",
        [_p("FXJANE", "FXDOE", lt="Broker")],
    ),
    ("8a lowercase", "hi i'm fxjane fxdoe, a licensed realtor. text me", [_p("FXJANE", "FXDOE")]),
    ("8b lowercase intro", "hi i'm Fxjane Fxdoe, a licensed realtor", [_p("FXJANE", "FXDOE")]),
    (
        "9 Military status",
        "I'm Fxjane Fxdoe, a licensed realtor.",
        [_p("FXJANE", "FXDOE", status="Military")],
    ),
]


def test_adv8_real_licensees_are_never_not_found(tmp_path):
    for i, (label, text, db) in enumerate(ADV8):
        assert _check(text, _client(db), tmp_path / str(i)).status is not LicenseStatus.NOT_FOUND, (
            label
        )
    # "Fxjo" is a prefix of FXJOANNA and "Fxlee" of FXLEEDS: substrings are not a match
    text, db = ADV8[0][1], ADV8[0][2]
    assert _check(text, _client(db), tmp_path / "leeds").status is LicenseStatus.NOT_CHECKED
    # the shapes a name lookup can read are supporting evidence
    by_label = {label: (text, db) for label, text, db in ADV8}
    for j, label in enumerate(
        ("2a family first, 2 tokens", "2c Korean", "5c paternal surname as middle")
    ):
        text, db = by_label[label]
        assert _check(text, _client(db), tmp_path / f"l{j}").status is LicenseStatus.LICENSED, label


def test_an_assistant_is_not_a_claim(tmp_path):
    seen: list = []
    text = "I'm Fxjane Fxdoe, the agent's assistant."
    assert detect_claim(text) is None
    assert detect_claim("I'm Fxjane Fxdoe, the agent\u2019s assistant.") is None
    assert _check(text, _client([], seen=seen), tmp_path).status is LicenseStatus.NOT_CHECKED
    assert seen == []


# the license number the ad itself gives (synthetic numbers)
def _number_db(status="Active", number="123456-SA", **kw):
    return [_p("FXJANE", "FXDOE", status=status, number=number, **kw)]


NUMBER_AD = "I'm Fxjane Fxdoe, a licensed realtor. TREC license # 123456. Zelle the deposit."


def test_a_license_number_not_on_file_or_not_active_is_not_found(tmp_path):
    assert _check(NUMBER_AD, _client([]), tmp_path).status is LicenseStatus.NOT_FOUND
    rows = _number_db(status="Expired more than 6 months")
    assert _check(NUMBER_AD, _client(rows), tmp_path / "b").status is LicenseStatus.NOT_FOUND
    assert _check("TREC 123456", _client([]), tmp_path / "c").status is LicenseStatus.NOT_FOUND


def test_a_license_number_on_an_active_license_with_the_name_is_licensed(tmp_path):
    for i, number in enumerate(("123456-SA", "123456-B", "123456")):
        result = _check(NUMBER_AD, _client(_number_db(number=number)), tmp_path / str(i))
        assert result.status is LicenseStatus.LICENSED, number
    # a number with no name in the ad cannot be tied to anyone: not an accusation, not support
    assert _check("TREC 123456", _client(_number_db()), tmp_path / "n").status is (
        LicenseStatus.NOT_CHECKED
    )
    # the surname alone is enough of a match
    other = "My name is Janet Fxdoe, a licensed agent. TREC #123456"
    assert _check(other, _client(_number_db()), tmp_path / "x").status is LicenseStatus.LICENSED


def test_a_license_number_under_another_name_is_not_checked(tmp_path):
    rows = [_p("FXZORA", "FXQUINN", number="123456-SA")]
    assert _check(NUMBER_AD, _client(rows), tmp_path).status is LicenseStatus.NOT_CHECKED
    # a 7-digit number whose prefix is ours is another license
    longer = [_p("FXJANE", "FXDOE", number="1234567-SA")]
    assert _check(NUMBER_AD, _client(longer), tmp_path / "b").status is LicenseStatus.NOT_FOUND


def test_only_a_trec_number_counts_as_a_license_number(tmp_path):
    seen: list = []
    for text in (
        "MLS #1234567 3/2 near campus",
        "Call 713-555-0100, unit #123456",
        "driver's license 1234567",
        "license plate 1234567",
        "TREC 12345",
        "Business license #5550123",
        "Insurance license #5550123",
        "TREC IABS. MLS# 5550123",
        "Fxjane Fxdoe, insurance agent. Insurance license #5550123. House for lease.",
    ):
        _check(text, _client([], seen=seen), tmp_path)
    assert seen == []


def test_the_license_number_is_never_sent_cached_or_logged_beyond_the_query(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    _check(
        NUMBER_AD,
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))),
        tmp_path,
    )
    assert "123456" not in caplog.text
    assert list(tmp_path.rglob("*")) == []  # a number lookup writes nothing


def test_two_slow_calls_do_not_starve_the_next_healthy_one(tmp_path, monkeypatch):
    from snapback.adapters import trec

    monkeypatch.setattr(trec, "TIMEOUT_S", 0.3)

    def slow(request: httpx.Request) -> httpx.Response:
        time.sleep(1.5)
        return httpx.Response(200, json=[])

    slow_client = httpx.Client(transport=httpx.MockTransport(slow))
    for i in range(2):
        text = f"Hi, I'm Fxslow{'bc'[i]} Fxperson, a licensed realtor."
        assert _check(text, slow_client, tmp_path / str(i)).status is LicenseStatus.NOT_CHECKED
    start = time.perf_counter()
    result = _check(CLAIM, _client([_row("Active")]), tmp_path / "healthy")
    assert result.status is LicenseStatus.LICENSED
    assert time.perf_counter() - start < 0.3


def test_more_than_25_exact_rows_with_a_fit_is_not_checked_not_licensed(tmp_path):
    rows = [_row("Active", first="FXNAME")] + [
        _row("Active", first=f"FX{i:02d}") for i in range(25)
    ]
    assert len(rows) == 26
    assert _check(CLAIM, _client(rows), tmp_path).status is LicenseStatus.NOT_CHECKED


def test_the_httpx_logger_never_carries_the_last_name(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    _check(CLAIM, _client([_row("Active")]), tmp_path)
    assert "FXPERSON" not in caplog.text.upper()


def test_a_not_checked_answer_is_never_cached(tmp_path):
    seen: list = []
    _check(CLAIM, _client(status=500, seen=seen), tmp_path)
    assert list(tmp_path.glob("*.json")) == []  # nothing written after the failed call
    again = _check(CLAIM, _client([_row("Active")], seen=seen), tmp_path)
    assert again.status is LicenseStatus.LICENSED  # not served from a cached NOT_CHECKED
    assert not any(
        json.loads(f.read_text())["status"] != "licensed" for f in tmp_path.glob("*.json")
    )


def test_the_cache_key_is_versioned(tmp_path):
    import hashlib

    _check(CLAIM, _client([_row("Active")]), tmp_path)
    old = hashlib.sha256(b"person|1|FXNAME|FXPERSON").hexdigest()[:32] + ".json"
    new = hashlib.sha256(b"v3|person|FXNAME|FXPERSON").hexdigest()[:32] + ".json"
    assert (tmp_path / new).is_file() and not (tmp_path / old).exists()


def test_a_name_then_a_line_break_is_not_one_name():
    assert detect_claim("Hi I'm Fxname\nFxperson, a licensed realtor") is None


def test_a_locator_after_a_name_is_not_a_self_claim():
    assert detect_claim("Fxzed Fxquick, Locator service") is None
    assert detect_claim("Fxzed Fxquick | Locator service") is None


def test_only_the_first_2000_characters_are_read():
    assert detect_claim("x" * 2100 + " I'm Fxname Fxperson, a licensed realtor.") is None
    assert detect_claim("x" * 100 + " I'm Fxname Fxperson, a licensed realtor.") is not None


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


def test_a_cache_file_that_is_not_licensed_is_never_trusted(tmp_path):
    import hashlib

    key = hashlib.sha256(b"v3|person|FXNAME|FXPERSON").hexdigest()[:32] + ".json"
    for i, status in enumerate(("not_found", "not_checked")):
        folder = tmp_path / str(i)
        folder.mkdir()
        (folder / key).write_text(json.dumps({"status": status, "sponsor": None}))
        result = _check(CLAIM, _client([_row("Active")]), folder)
        assert result.status is LicenseStatus.LICENSED, status  # asked again, not read back


def test_a_license_number_written_with_a_leading_zero_matches_the_stored_one(tmp_path):
    ad = "I'm Fxjane Fxdoe, a licensed realtor. TREC License #0612345"
    seen: list = []
    rows = _number_db(number="612345-SA")
    result = _check(ad, _client(rows, seen=seen), tmp_path)
    assert result.status is LicenseStatus.LICENSED
    assert "'612345%'" in seen[0].url.params["$where"]
    # not on file after stripping: still NOT_FOUND, never a false hit on the zero-padded text
    assert _check(ad, _client([]), tmp_path / "b").status is LicenseStatus.NOT_FOUND
    # all zeros is no license number at all
    zero_seen: list = []
    zeros = _check("TREC License #0000000", _client([], seen=zero_seen), tmp_path / "c")
    assert zeros.status is LicenseStatus.NOT_CHECKED and zero_seen == []


def test_a_number_active_under_another_name_is_final_not_checked(tmp_path):
    db = [
        _p("FXJOHN", "FXDOE", number="111111-SA"),
        _p("FXALICE", "FXKING", number="333333-SA"),
        _p("FXJOHN", "FXROE", number="222222-SA"),  # the claimed person IS licensed...
    ]
    seen: list = []
    a = _check(
        "Hi, I'm Fxjohn Fxroe, a licensed realtor. TREC #111111", _client(db, seen=seen), tmp_path
    )
    assert a.status is LicenseStatus.NOT_CHECKED  # ...but the number is another agent's
    assert len(seen) == 1  # no fall-through to a name lookup
    b = _check(
        "Hi, I'm Fxjohn Fxroe, a licensed realtor. TREC #333333", _client(db), tmp_path / "b"
    )
    assert b.status is LicenseStatus.NOT_CHECKED
    # one shared first name is not enough; the last name is
    c = _check("I'm Fxjohn Fxroe, a licensed realtor. TREC #111111", _client(db), tmp_path / "c")
    assert c.status is LicenseStatus.NOT_CHECKED
    d = _check("I'm Fxjane Fxdoe, a licensed realtor. TREC #111111", _client(db), tmp_path / "d")
    assert d.status is LicenseStatus.LICENSED  # the last name matches


def test_a_license_next_to_a_role_word_counts_as_a_license_number(tmp_path):
    ad = "Fxjane Fxdoe, realtor. License 123456. Call anytime."
    assert _check(ad, _client([]), tmp_path).status is LicenseStatus.NOT_FOUND
    rows = _number_db()
    assert _check(ad, _client(rows), tmp_path / "b").status is LicenseStatus.LICENSED
    # the same number with nothing real-estate near it is just a number
    assert _check("Pool license 123456", _client([]), tmp_path / "c").status is (
        LicenseStatus.NOT_CHECKED
    )


def test_a_number_in_other_words_after_trec_is_not_a_license_number():
    from snapback.adapters.trec import _license_number

    for text in (
        "I'm Fxjohn Fxdoe, a licensed realtor. TREC licensed, 555012 sq ft",
        "TREC approved, 1234567 views",
    ):
        assert _license_number(text) is None, text
    assert _license_number("TREC lic. no. 0123456") == "123456"
    assert _license_number("Realtor, license: 1234567-B") == "1234567"

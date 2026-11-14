"""D12 #130: HCAD owner of record for the kit Houston houses. Synthetic files only: no real
names, addresses or parcel ids. A person's name never reaches the output or the lookup file."""

import json
import subprocess
from pathlib import Path

import pytest

from snapback.adapters.hcad import build_subset, owner, probe_columns
from snapback.contracts import OwnerKind, OwnerMatch

OWNERS = "acct\tln_num\tname\taka\tpct_own\n" + "\n".join(
    [
        "fx0001\t1\tFXAMPLE HOMES LLC\t\t100",
        "fx0002\t1\tFXPERSON FXNAME Q\t\t100",
        "fx0003\t1\tFXPERSON FAMILY TRUST\t\t100",
        "fx0004\t1\tFXOTHER FXJANE\t\t100",
    ]
)
REAL_ACCT = "acct\tyr\tsite_addr_1\tsite_addr_2\tsite_addr_3\n" + "\n".join(
    [
        "fx0001\t2026\t100 FIXTURE LN\tHOUSTON\t00001",
        "fx0002\t2026\t200 SAMPLE ST\tHOUSTON\t00001",
        "fx0003\t2026\t300 EXAMPLE AVE\tHOUSTON\t00001",
        "fx0004\t2026\t999 NOT IN KIT RD\tHOUSTON\t00001",
    ]
)
KIT_STREETS = ["100 Fixture Lane", "200 Sample Street", "300 Example Avenue"]


def _hcad(tmp_path: Path) -> Path:
    folder = tmp_path / "hcad"
    folder.mkdir()
    (folder / "owners.txt").write_text(OWNERS, encoding="utf-8")
    (folder / "real_acct.txt").write_text(REAL_ACCT, encoding="utf-8")
    return folder


def _subset(tmp_path: Path) -> Path:
    out = tmp_path / "data" / "hcad" / "owner_subset.jsonl"
    build_subset(_hcad(tmp_path), KIT_STREETS, out, salt="fx-salt")
    return out


def test_a_company_we_do_not_know_is_sent_with_no_name(tmp_path):
    # round 5 on #160: only a company we already know is named; any other is "a company owner"
    result = owner("2 bed at 100 Fixture Ln, Houston", _subset(tmp_path), salt="fx-salt")
    assert result is not None and result.kind is OwnerKind.COMPANY
    assert (result.company, result.company_known) == (None, False)
    assert "FXAMPLE" not in result.model_dump_json().upper()


def test_a_company_in_the_published_rule_table_is_named_by_the_table(tmp_path, monkeypatch):
    from datetime import date

    from snapback.agent.rules import published

    row = published.PublishedRuleRow(
        company="Fxample Homes",
        rule="we only take applications on fxample.example",
        source_url="https://fxample.example/fraud",
        checked_on=date(2026, 11, 14),
    )
    monkeypatch.setattr(published, "PUBLISHED_RULES", (row,))
    result = owner("2 bed at 100 Fixture Ln", _subset(tmp_path), salt="fx-salt")
    # the table's own name, never the county roll's string
    assert (result.company, result.company_known) == ("Fxample Homes", True)


def test_a_company_that_is_an_office_on_record_in_the_kit_is_named_by_the_kit(tmp_path):
    subset = _subset(tmp_path)
    result = owner("2 bed at 100 Fixture Ln", subset, salt="fx-salt", known=["Fxample Homes"])
    assert (result.company, result.company_known) == ("Fxample Homes", True)
    # an office that only shares a later word is not the owner
    other = owner("2 bed at 100 Fixture Ln", subset, salt="fx-salt", known=["Homes Of Fxample"])
    assert (other.company, other.company_known) == (None, False)


def test_a_person_owner_gives_yes_or_no_only(tmp_path):
    subset = _subset(tmp_path)
    same = owner("200 Sample St. My name is Fxname Fxperson.", subset, salt="fx-salt")
    assert same.kind is OwnerKind.PERSON and same.company is None
    assert same.poster_matches is OwnerMatch.YES
    other = owner("200 Sample St. My name is Fxbob Fxsmith.", subset, salt="fx-salt")
    assert other.poster_matches is OwnerMatch.NO
    unnamed = owner("200 Sample St, available now", subset, salt="fx-salt")
    assert unnamed.poster_matches is OwnerMatch.NOT_CHECKED


def test_no_person_name_anywhere_in_output_or_lookup_file(tmp_path):
    subset = _subset(tmp_path)
    result = owner("200 Sample St. My name is Fxname Fxperson.", subset, salt="fx-salt")
    for text in (result.model_dump_json(), subset.read_text(encoding="utf-8")):
        upper = text.upper()
        assert "FXPERSON" not in upper and "FXNAME" not in upper and "FXJANE" not in upper
        assert "SAMPLE" not in upper and "FX0002" not in upper  # no address or parcel id either


def test_a_family_trust_is_a_private_owner_not_a_company(tmp_path):
    result = owner("300 Example Avenue", _subset(tmp_path), salt="fx-salt")
    assert result.kind is OwnerKind.PERSON and result.company is None


def test_an_unknown_address_is_none(tmp_path):
    subset = _subset(tmp_path)
    assert owner("5 Nowhere Road, Houston", subset, salt="fx-salt") is None
    assert owner("999 Not In Kit Rd", subset, salt="fx-salt") is None  # filtered out


def test_no_subset_file_is_none(tmp_path):
    assert owner("100 Fixture Ln", tmp_path / "missing.jsonl", salt="fx-salt") is None


def test_the_probe_prints_column_names_only(tmp_path):
    cols = probe_columns(_hcad(tmp_path))
    assert cols["owners.txt"] == ["acct", "ln_num", "name", "aka", "pct_own"]
    assert "FXPERSON" not in json.dumps(cols)


def test_the_lookup_file_is_never_staged():
    repo = Path(__file__).resolve().parents[1]
    target = repo / "data" / "hcad" / "owner_subset.jsonl"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(target)], cwd=repo, check=False
    ).returncode
    assert ignored == 0


def test_lookup_owner_reads_the_settings_data_dir(tmp_path, monkeypatch):
    from snapback.adapters import hcad

    monkeypatch.setenv("SNAPBACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("snapback.agent.rules.contact.phone_salt", lambda *a, **k: "fx-salt")
    from snapback.settings import get_settings

    get_settings.cache_clear()
    try:
        _subset(tmp_path)
        result = hcad.lookup_owner("100 Fixture Ln")
        assert result is not None and result.kind is OwnerKind.COMPANY
    finally:
        get_settings.cache_clear()


def test_a_company_without_a_name_is_a_company_owner_with_no_name(tmp_path):
    subset = tmp_path / "data" / "hcad" / "owner_subset.jsonl"
    subset.parent.mkdir(parents=True)
    import hashlib

    from snapback.adapters.costar_residential import normalize_address

    key = hashlib.sha256(normalize_address("100 Fixture Ln").encode()).hexdigest()
    subset.write_text(json.dumps({"key": key, "kind": "company", "company": ""}) + "\n")
    result = owner("100 Fixture Ln", subset, salt="fx-salt")
    assert result.kind is OwnerKind.COMPANY and result.company is None  # "a company owner"


def test_kit_lookups_owner_reads_the_hcad_lookup(tmp_path, monkeypatch):
    from snapback.agent.join import KitLookups
    from snapback.contracts import DataSource
    from snapback.settings import get_settings

    monkeypatch.setenv("SNAPBACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("snapback.agent.rules.contact.phone_salt", lambda *a, **k: "fx-salt")
    get_settings.cache_clear()
    try:
        _subset(tmp_path)
        lookups = KitLookups(DataSource.LIVE)
        result = lookups.owner("2 bed at 100 Fixture Ln")
        assert result is not None and result.kind is OwnerKind.COMPANY
        assert (result.company, result.company_known) == (None, False)  # not one we know
        assert result.poster_says_owner is False and result.published_rule is None  # lane A's
        assert lookups.owner("5 Nowhere Road") is None
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "name",
    [
        "FXDOE FXJON TRUST",
        "FXDOE FXJON REV TRUST",
        "FXDOE FXJON & FXMARY CO-TRUSTEES",
        "FXDOE FXJON TESTAMENTARY TRUST",
        "FXDOE 2015 TRUST",
        "FXDOE CHILDRENS TRUST",
        "FXDOE SEPARATE PROPERTY TRUST",
        "FXDOE FXJON DECLARATION OF TRUST",
        "FXDOE FXJON TR",
        "CHURCH FXJON",
        "STATE FXJON",
        "CITY FXJON Q",
        # round 2: a company marker plus a person segment is still a private owner
        "FIRST FXBANK TRUST COMPANY TR FXDOE FXJON FAMILY TRUST",
        "FXAMPLE TRUST COMPANY TRUSTEE FOR FXDOE FXJON",
        "FXDOE FXJON & FXCO PROPERTIES LLC",
        "FXDOE FXJON DBA FXDOE HOMES",
        "FXDOE FXJON C/O FXCO MANAGEMENT",
        "FXDOE N A TRUST",
        "BANK FXJON",
        "FXDOE FXJON & FXMARY CHURCH",
        "FXDOE FXJON ET AL",
        "FXBANK NATIONAL ASSOCIATION TRUSTEE",
        "FXBANK N.A. TR",
        "FXAMPLE RENTAL TRUST LLC",
        # round 3: the shape decides, not a marker list
        "FXDOE FXJON AND FXCO PROPERTIES LLC",
        "FXCO HOMES LLC AND FXDOE FXJON",
        "FXAMPLE TRUST COMPANY CUSTODIAN FBO FXDOE FXJON IRA",
        "FXCO INC CUSTODIAN FBO FXDOE FXJON",
        "FXAMPLE TRUST COMPANY TTEE FXDOE FXJON",
        "FXDOE FXJON TRSTE FXCO BANK",
        "FXDOE FXJON / FXCO LLC",
        "FXDOE FXJON + FXCO LLC",
        "FXDOE FXJON, FXCO LLC",
        "FXCO LLC % FXDOE FXJON",
        "FXCO LLC ATTN FXDOE FXJON",
        "FXDOE FXJON C / O FXCO LLC",
        "FXDOE FXJON H/E FXCO LLC",
        "FXDOE FXJON ESTATE OF FXCO LLC",
        "FXDOE FXJON LLC ETAL",
        "FXDOE LLC FXJON",
        "FXDOE FXJON JR LLC",
        "FXJON FXDOE ESTATE LLC",
        "FXDOE FXJON IRA LLC",
        "FXDOE N A",
        "FXDOE FXJON N A",
        "REIT FXJON",
        "HOMES FXJON",
        "CAPITAL FXJON A",
        "FXBANK N.A.",
        # round 4: an institution form never outranks a person token
        "STATE OF TEXAS FBO FXDOE FXJON",
        "CITY OF HOUSTON AND FXDOE FXJON",
        "COUNTY OF HARRIS TRUSTEE FOR FXDOE FXJON",
        "CITY OF HOUSTON ATTN FXDOE FXJON ESTATE",
        # round 4: more tokens that name or act for a person
        "FXDOE FXJON ETUX FXCO LLC",
        "FXDOE FXJON ETVIR FXCO LLC",
        "FXDOE FXJON AKA FXCO LLC",
        "FXDOE FXJON FKA FXCO LLC",
        "FXDOE FXJON NKA FXCO LLC",
        "FXDOE FXJON OR FXCO LLC",
        "FXDOE FXJON CARE FXCO LLC",
        "FXDOE HEIRS FXCO LLC",
        "FXDOE FXJON EXECUTOR FXCO LLC",
        "FXDOE FXJON EXECUTRIX FXCO LLC",
        "FXDOE FXJON ADMINISTRATOR FXCO LLC",
        "FXDOE FXJON GUARDIAN FXCO LLC",
        "FXDOE FXJON TENANT FXCO LLC",
        "FXDOE FXJON MGR FXCO LLC",
        "FXDOE FXJON OF FXCO LLC",
        "FXDOE A.N.D. FXCO LLC",
        "FXDOE FXJON E.T. A.L. FXCO LLC",
        "FXDOE FXJON - FXCO LLC",
        "FXDOE FXJON . FXCO LLC",
        "FXDOE FXJON FXCO LLC-",
        # round 5: exactly one word after OF, separators with no letter, more person tokens
        "CITY OF HOUSTON FXDOE FXJON",
        "FXDOE FXJON -- FXCO LLC",
        "FXDOE FXJON .. FXCO LLC",
        "FXDOE FXJON CUST FXCO LLC",
        "FXDOE FXJON EXEC FXCO LLC",
        "FXDOE FXJON TTEES FXCO LLC",
        "FXDOE FXJON GDN FXCO LLC",
        "FXDOE FXJON POA FXCO LLC",
        "FXCO LLC UTMA FXDOE FXJON",
        "FXCO LLC BY FXDOE FXJON",
        "FXCO LLC WITH FXDOE FXJON",
    ],
)
def test_a_name_that_carries_a_person_is_a_private_owner(name):
    from snapback.adapters.hcad import classify

    assert classify(name) is OwnerKind.PERSON


@pytest.mark.parametrize(
    "name",
    [
        "FXAMPLE TRUST COMPANY",
        "FXAMPLE BANK N.A.",
        "FXAMPLE HOMES LLC",
        "FXDOE HOMES LLC",
        "FXDOE FXJON MANAGEMENT",
        "FXAMPLE NATIONAL ASSOCIATION",
        "FXAMPLE CHURCH OF CHRIST",
        "CITY OF FXTOWN",
        "CITY OF HOUSTON",
        "STATE OF TEXAS",
        "FIRST FXAMPLE CHURCH",
    ],
)
def test_institutions_are_companies(name):
    from snapback.adapters.hcad import classify

    assert classify(name) is OwnerKind.COMPANY


def test_two_accounts_on_one_site_address_give_no_owner(tmp_path):
    folder = tmp_path / "hcad"
    folder.mkdir()
    (folder / "owners.txt").write_text(
        "acct\tln_num\tname\nfx1\t1\tFXAMPLE HOMES LLC\nfx2\t1\tFXOTHER HOMES LLC\n",
        encoding="utf-8",
    )
    (folder / "real_acct.txt").write_text(
        "acct\tsite_addr_1\tsite_addr_2\n"
        "fx1\t100 FIXTURE LN\tHOUSTON\n"
        "fx2\t100 FIXTURE LN\tHOUSTON\n",
        encoding="utf-8",
    )
    out = tmp_path / "data" / "hcad" / "owner_subset.jsonl"
    build_subset(folder, ["100 Fixture Lane"], out, salt="fx-salt")
    assert owner("100 Fixture Ln", out, salt="fx-salt") is None


def test_two_kit_streets_in_one_listing_give_no_owner(tmp_path):
    subset = _subset(tmp_path)
    assert owner("100 Fixture Ln or 200 Sample St, your pick", subset, salt="fx-salt") is None


@pytest.mark.parametrize(
    "text",
    [
        "200 Sample St. This is Spacious Home for families.",
        "200 Sample St. I'm Relocating For Work.",
        "200 Sample St, call today - Move In",
    ],
)
def test_phrases_are_not_read_as_the_posters_name(tmp_path, text):
    result = owner(text, _subset(tmp_path), salt="fx-salt")
    assert result is not None and result.poster_matches is OwnerMatch.NOT_CHECKED


def test_a_nickname_with_the_right_last_name_is_not_checked_not_no(tmp_path):
    result = owner("200 Sample St. My name is Johnny Fxperson.", _subset(tmp_path), salt="fx-salt")
    assert result.poster_matches is OwnerMatch.NOT_CHECKED


def test_a_different_salt_gives_not_checked_never_no(tmp_path):
    subset = _subset(tmp_path)
    result = owner("200 Sample St. My name is Fxbob Fxsmith.", subset, salt="fx-other-salt")
    assert result is not None and result.poster_matches is OwnerMatch.NOT_CHECKED


@pytest.mark.parametrize(
    "text",
    [
        "200 Sample St. I'm the owner. Pets ok - No Smoking",
        "200 Sample St. I'm the owner. Rent includes - Water Paid",
    ],
)
def test_a_signature_never_gives_no(tmp_path, text):
    result = owner(text, _subset(tmp_path), salt="fx-salt")
    assert result is not None and result.poster_matches is not OwnerMatch.NO


def test_a_signature_can_still_say_yes(tmp_path):
    result = owner("200 Sample St, call me. - Fxname Fxperson", _subset(tmp_path), salt="fx-salt")
    assert result.poster_matches is OwnerMatch.YES

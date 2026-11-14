"""D12 #130: HCAD owner of record for the kit Houston houses. Synthetic files only: no real
names, addresses or parcel ids. A person's name never reaches the output or the lookup file."""

import json
import subprocess
from pathlib import Path

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


def test_a_company_owner_is_returned_by_name(tmp_path):
    result = owner("2 bed at 100 Fixture Ln, Houston", _subset(tmp_path), salt="fx-salt")
    assert result is not None and result.kind is OwnerKind.COMPANY
    assert result.company == "FXAMPLE HOMES LLC"


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

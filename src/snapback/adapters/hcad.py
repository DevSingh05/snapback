"""D12 (lane D, #130): owner of record for the kit's Houston houses, from HCAD's public data.

Run once, on the machine that has the kit and HCAD's `Real_acct_owner` files, into the git-ignored
`data/` folder (cleared on #130, ruling 02:22):
    uv run python -m snapback.adapters.hcad --hcad <folder or zip> --kit <kit>
It keeps only the HCAD rows whose site address is a kit Houston house, and writes
`data/hcad/owner_subset.jsonl`. `make purge` deletes it. The local lookup holds:
- a hash of the normalised street (never the address, never the parcel id);
- the owner kind: a company or institution, or a private owner (a family or living trust is a
  private owner, since it carries a person's name);
- the company name, for a company only;
- for a private owner, keyed hashes of the name's words (HMAC with the shared phone salt), so the
  poster's name can be compared without any person's name being kept.

`owner(listing_text)` returns the contract's `OwnerResult` (approved on #41): `kind`, `company`
and `poster_matches` (yes / no / not_checked). Lane A fills the rest. None means no owner data.

Column names are read from each file's header row, not assumed; `--probe` prints the header
names only, so they can be checked on the real files before the first run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import re
import sys
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from snapback.adapters.costar_residential import normalize_address
from snapback.contracts import OwnerKind, OwnerMatch, OwnerResult

OWNERS_FILE = "owners.txt"
ACCOUNTS_FILE = "real_acct.txt"
SUBSET = Path("hcad") / "owner_subset.jsonl"
HOUSTON = "HOUSTON"

ACCT = ["acct", "account"]
NAME = ["name", "owner_name", "ownername"]
STREET = ["site_addr_1", "site_address", "site_addr"]
CITY = ["site_addr_2", "site_city"]

# A whole word from this set makes the owner a company or institution. Not here on purpose: a
# bare CO (left by "CO-TRUSTEES"), and CHURCH / CITY / STATE / COUNTY, which are surnames too and
# count only in an institution pattern (see `classify`).
_COMPANY_WORDS = {
    "LLC", "INC", "INCORPORATED", "LP", "LLP", "LTD", "CORP", "CORPORATION", "COMPANY", "BANK",
    "PROPERTIES", "PROPERTY", "HOMES", "REIT", "ASSOCIATION", "ASSN", "PARTNERS", "PARTNERSHIP",
    "FUND", "HOLDINGS", "INVESTMENTS", "CAPITAL", "GROUP", "REALTY", "MANAGEMENT", "AUTHORITY",
    "DISTRICT", "VENTURES", "ENTERPRISES", "SERVICES", "BORROWER", "OPENDOOR", "OFFERPAD",
}  # fmt: skip
# Any of these makes the name a trust, and a trust is a private owner (it carries a person's
# name) unless an unambiguous institution marker is also there
_TRUST_WORDS = {"TRUST", "TR", "TRUSTEE", "TRUSTEES", "TRS"}
_INSTITUTION_MARKERS = {"BANK", "LLC", "INC", "LP", "REIT"}
_MY_NAME = re.compile(
    r"(?i:\bmy[ \t]+name[ \t]+is)[ \t]+([A-Z][A-Za-z'\-]{1,30})[ \t]+([A-Z][A-Za-z'\-]{1,30})"
)
_SIGNATURE = re.compile(
    r"[-\u2013\u2014][ \t]*([A-Z][A-Za-z'\-]{1,30})[ \t]+([A-Z][A-Za-z'\-]{1,30})[ \t]*$"
)
# Words that start slogans after a dash, never a person's name
_NOT_NAMES = {
    "HOME", "HOUSE", "MOVE", "FOR", "RELOCATING", "CALL", "TEXT", "AVAILABLE", "SPACIOUS",
    "LOVELY", "BEAUTIFUL", "NEW", "GREAT", "PRIVATE", "OWNER", "LANDLORD", "RENT", "LEASE",
    "TODAY", "NOW", "THANKS", "THANK", "CONTACT", "APPLY", "VIEW", "TOUR", "READY",
}  # fmt: skip
_MAX_TEXT = 2_000
FINGERPRINT_INPUT = b"snapback-hcad-salt-fingerprint"


def _key(street: str) -> str:
    return hashlib.sha256(normalize_address(street).encode()).hexdigest()


def _token_hash(word: str, salt: str) -> str:
    return hmac.new(salt.encode(), word.upper().encode(), hashlib.sha256).hexdigest()


def _salt_fingerprint(salt: str) -> str:
    return hmac.new(salt.encode(), FINGERPRINT_INPUT, hashlib.sha256).hexdigest()


def classify(owner_name: str) -> OwnerKind:
    """A company or institution, or a private owner. When in doubt, a private owner: then the
    card says "a private owner" and no name can be shown."""
    tokens = re.findall(r"[A-Z0-9&]+", owner_name.upper())  # hyphens and dots split words
    words = set(tokens)
    joined = " ".join(tokens)
    if words & _TRUST_WORDS:
        institution = (
            words & _INSTITUTION_MARKERS
            or "TRUST COMPANY" in joined
            or "NATIONAL ASSOCIATION" in joined
            or re.search(r"\bN A\b", joined) is not None  # N.A.
        )
        return OwnerKind.COMPANY if institution else OwnerKind.PERSON
    if re.match(r"(CITY|STATE|COUNTY) OF\b", joined) or (tokens and tokens[-1] == "CHURCH"):
        return OwnerKind.COMPANY
    return OwnerKind.COMPANY if words & _COMPANY_WORDS else OwnerKind.PERSON


def _rows(source: Path, name: str) -> Iterator[dict[str, str]]:
    """Tab-delimited rows of one HCAD file, from a folder or from inside a zip."""
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            member = next(m for m in archive.namelist() if m.lower().endswith(name))
            with archive.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                yield from csv.DictReader(text, delimiter="\t")
        return
    with (source / name).open(encoding="latin-1", newline="") as fh:
        yield from csv.DictReader(fh, delimiter="\t")


def _col(row: dict[str, str], names: list[str]) -> str:
    for n in names:
        for key in row:
            if key and key.strip().lower() == n:
                return (row[key] or "").strip()
    return ""


def probe_columns(source: Path) -> dict[str, list[str]]:
    """Header names only, never a value."""
    out = {}
    for name in (OWNERS_FILE, ACCOUNTS_FILE):
        first = next(_rows(source, name), {})
        out[name] = [k.strip() for k in first]
    return out


def build_subset(source: Path, kit_streets: Iterable[str], out: Path, salt: str) -> int:
    """Keep only kit Houston houses; write hashed keys, kinds and company names. Returns rows."""
    wanted = {_key(s) for s in kit_streets}
    accounts: dict[str, str] = {}
    for row in _rows(source, ACCOUNTS_FILE):
        city = _col(row, CITY).upper()
        if city and city != HOUSTON:
            continue
        key = _key(_col(row, STREET))
        if key in wanted:
            accounts[_col(row, ACCT)] = key
    owners: dict[str, list[str]] = {}
    for row in _rows(source, OWNERS_FILE):
        acct = _col(row, ACCT)
        if acct in accounts:
            owners.setdefault(acct, []).append(_col(row, NAME))
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as fh:
        # first line: which salt keyed the name hashes, so a server with another salt says
        # NOT_CHECKED rather than a false NO
        fh.write(json.dumps({"salt_fingerprint": _salt_fingerprint(salt)}) + "\n")
        for acct, names in owners.items():
            primary = names[0]
            kind = classify(primary)
            entry: dict[str, object] = {"key": accounts[acct], "kind": kind.value}
            if kind is OwnerKind.COMPANY:
                entry["company"] = primary
            else:
                words = {w for n in names for w in re.findall(r"[A-Z]{2,}", n.upper())}
                entry["name_words"] = sorted(_token_hash(w, salt) for w in words)
            fh.write(json.dumps(entry) + "\n")
            count += 1
    return count


def _poster_name(text: str) -> tuple[str, str] | None:
    """The poster's own name: only 'my name is' or a signature at the end, never a bare
    "I'm" / "this is" (which read 'I'm Relocating For Work' as a name)."""
    for m in (_MY_NAME.search(text), _SIGNATURE.search(text.strip())):
        if m and not {m.group(1).upper(), m.group(2).upper()} & _NOT_NAMES:
            return m.group(1), m.group(2)
    return None


def _street_windows(text: str) -> Iterator[str]:
    """Every run of 2 to 6 words starting with a house number: the street, if there is one."""
    words = normalize_address(text).split()
    for i, w in enumerate(words):
        if w.isdigit():
            for n in range(2, 7):
                if i + n <= len(words):
                    yield " ".join(words[i : i + n])


def owner(listing_text: str, subset: Path, salt: str) -> OwnerResult | None:
    if not subset.is_file():
        return None
    text = listing_text[:_MAX_TEXT]
    keys = {hashlib.sha256(w.encode()).hexdigest() for w in _street_windows(text)}
    try:
        rows = [json.loads(line) for line in subset.read_text(encoding="utf-8").splitlines()]
    except (OSError, ValueError):
        return None
    fingerprint = next((r.get("salt_fingerprint") for r in rows if "salt_fingerprint" in r), None)
    found = [r for r in rows if r.get("key") in keys]
    if len(found) != 1:
        return None  # no match, or two accounts / two kit streets: never pick one at random
    entry = found[0]
    if entry.get("kind") == OwnerKind.COMPANY.value:
        company = (entry.get("company") or "").strip()
        if not company:
            return None  # a company owner is never sent without its name (A19 review)
        return OwnerResult(kind=OwnerKind.COMPANY, company=company)
    name = _poster_name(text)
    if name is None or fingerprint != _salt_fingerprint(salt):
        # no name to compare, or the lookup was keyed with another salt: never a false NO
        return OwnerResult(kind=OwnerKind.PERSON)
    owned = set(entry.get("name_words") or [])
    first, last = (_token_hash(n, salt) in owned for n in name)
    if first and last:
        matches = OwnerMatch.YES
    elif first or last:
        matches = OwnerMatch.NOT_CHECKED  # a nickname, or a shared last name: not a NO
    else:
        matches = OwnerMatch.NO
    return OwnerResult(kind=OwnerKind.PERSON, poster_matches=matches)


def lookup_owner(listing_text: str) -> OwnerResult | None:
    """The entry point lane A's `KitLookups.owner` calls: the lookup under SNAPBACK_DATA_DIR and
    the shared phone salt (set SNAPBACK_PHONE_SALT so the lookup and the check agree)."""
    from snapback.agent.rules.contact import phone_salt
    from snapback.safety.paths import resolve_data_dir
    from snapback.settings import get_settings

    subset = resolve_data_dir(get_settings().snapback_data_dir) / SUBSET
    return owner(listing_text, subset, phone_salt())


def main(argv: list[str] | None = None) -> None:
    from snapback.adapters.costar_jsonl import DEFAULT_KIT, _find, _first, _iter_jsonl
    from snapback.adapters.costar_residential import RESIDENTIAL_FIELDS, RESIDENTIAL_FILE
    from snapback.agent.rules.contact import phone_salt
    from snapback.safety.paths import resolve_data_dir

    parser = argparse.ArgumentParser(description="HCAD owner subset for the kit Houston houses.")
    parser.add_argument("--hcad", type=Path, required=True, help="Real_acct_owner folder or zip")
    parser.add_argument("--kit", type=Path, default=DEFAULT_KIT)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--probe", action="store_true", help="print column names only")
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(probe_columns(args.hcad), indent=2))
        return
    path = _find(args.kit, RESIDENTIAL_FILE)
    if path is None:
        print(f"kit not found ({RESIDENTIAL_FILE})")
        sys.exit(1)
    streets = [
        s for rec in _iter_jsonl(path)
        if isinstance(s := _first(rec, RESIDENTIAL_FIELDS["street"]), str)
    ]  # fmt: skip
    out = resolve_data_dir(args.data) / SUBSET
    kept = build_subset(args.hcad, streets, out, phone_salt())
    written = f"data/{SUBSET.as_posix()}"
    print(f"owner subset: {kept} houses of {len(streets)} kit addresses; written to {written}")


if __name__ == "__main__":
    main()

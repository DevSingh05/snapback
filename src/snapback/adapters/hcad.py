"""D12 (lane D, #130): owner of record for Harris County homes, from HCAD's public data.

Run once, on the machine that has the kit and HCAD's `Real_acct_owner` files, into the git-ignored
`data/` folder (cleared on #130, ruling 02:22):
    uv run python -m snapback.adapters.hcad --hcad <folder or zip> --kit <kit>
With `--all-harris` it keeps every HCAD account (the owner check then covers any Harris County
address the ad names); with `--kit` it keeps only the rows whose site address is a kit Houston
house. Either way it writes `data/hcad/owner_subset.jsonl`, sorted by street hash so a lookup is a
binary search, not a read of the whole file. `make purge` deletes it. The local lookup holds:
- a hash of the normalised street (never the address, never the parcel id);
- the owner kind: a company or institution, or a private owner (a family or living trust is a
  private owner, since it carries a person's name);
- the company name, for a company only;
- for a private owner, keyed hashes of the name's words (HMAC with the shared phone salt), so the
  poster's name can be compared without any person's name being kept.

`owner(listing_text)` returns the contract's `OwnerResult` (approved on #41): `kind`, `company`,
`company_known` and `poster_matches` (yes / no / not_checked). Lane A fills the rest. None means
no owner data. A company is named only when it is one we already know: a row in the
published-rule table, or an office on record in the kit, and then by that entry's own name. Any
other company goes out with no name, and the card says "a company owner" (round 5 on #160).

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
from typing import BinaryIO

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

# Owner kind is decided by the shape of the name, not by a list of blocked markers (conductor
# ruling 07:28 on #160). When unsure, a private owner: then no name can reach the card.
_ALLOWED_CHARS = re.compile(r"[A-Za-z0-9 .\-']+")
_PERSON_TOKENS = {
    "AND", "FBO", "CUSTODIAN", "ATTN", "TTEE", "TRSTE", "TRST", "TRUSTE", "ETAL", "ET", "EST",
    "ESTATE", "IRA", "AS", "AGENT", "JR", "SR", "II", "III", "IV", "UX", "FAMILY", "LIVING",
    "TRUST", "TR", "TRS", "TRUSTEE", "TRUSTEES", "DBA", "FOR", "ETUX", "ETVIR", "AKA", "FKA",
    "NKA", "OR", "CARE", "HEIRS", "EXECUTOR", "EXECUTRIX", "ADMINISTRATOR", "GUARDIAN",
    "TENANT", "MGR", "CUST", "EXEC", "TTEES", "GDN", "POA", "UTMA", "BY", "WITH",
}  # fmt: skip
_ENTITY_SUFFIXES = {"LLC", "INC", "LP", "LTD", "CORP", "CO", "REIT"}
_COMPANY_LAST_WORDS = {
    "HOMES", "PROPERTIES", "HOLDINGS", "MANAGEMENT", "REALTY", "CAPITAL", "INVESTMENTS",
    "GROUP", "PARTNERS", "BANK", "ASSOCIATION", "AUTHORITY",
}  # fmt: skip
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
    """COMPANY only when the whole name has the shape of one company or institution: an entity
    suffix or company word as the last word, or an institution form. Everything else, and every
    name that joins, names or acts for a person, is a private owner."""
    name = owner_name.strip().upper()
    if not name or not _ALLOWED_CHARS.fullmatch(name):
        return OwnerKind.PERSON  # '&', '/', '+', ',', '%' ... join or point at another party
    if name.endswith("-") or any(not re.search(r"[A-Z0-9]", part) for part in name.split()):
        return OwnerKind.PERSON  # a separator with no letter ('-', '--', '..'), or a cut-off name
    # dotted single letters (A.N.D., E.T. A.L.) spell a joining word; only N.A. after BANK or
    # ASSOCIATION is allowed, and only at the end
    dotted = re.sub(r"\b(BANK|ASSOCIATION) N\.\s*A\.?$", r"\1", name)
    if re.search(r"\b[A-Z]\.\s*[A-Z]\.", dotted):
        return OwnerKind.PERSON
    tokens = re.findall(r"[A-Z0-9']+", name)  # spaces, dots and hyphens split words
    joined = " ".join(tokens)
    trust_company = joined.endswith(" TRUST COMPANY")
    words = tokens[:-2] if trust_company else tokens  # TRUST in "... TRUST COMPANY" is not a trust
    # person tokens outrank every institution form ("STATE OF TEXAS FBO ..." is a person)
    if set(words) & _PERSON_TOKENS:
        return OwnerKind.PERSON
    institution_of = re.fullmatch(r"(CITY|STATE|COUNTY) OF \w+", joined)  # one word after OF
    church_of = re.fullmatch(r"\w+( \w+)* CHURCH( OF \w+)?", joined)
    if "OF" in tokens and not (institution_of or church_of):
        return OwnerKind.PERSON  # "... OF FXCO LLC": of-before-an-entity names a person
    if institution_of or trust_company or church_of:
        return OwnerKind.COMPANY
    if len(tokens) < 2:
        return OwnerKind.PERSON  # no company word counts in position 0
    if tokens[-2:] == ["N", "A"]:
        return (
            OwnerKind.COMPANY
            if len(tokens) >= 3 and tokens[-3] in {"BANK", "ASSOCIATION"}
            else OwnerKind.PERSON
        )
    last = tokens[-1]
    if last in _ENTITY_SUFFIXES or last in _COMPANY_LAST_WORDS:
        return OwnerKind.COMPANY
    return OwnerKind.PERSON


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


def build_subset(source: Path, kit_streets: Iterable[str] | None, out: Path, salt: str) -> int:
    """Write hashed keys, kinds and company names, sorted by key. Returns rows.

    `kit_streets` keeps only those Houston houses. None keeps every account in the county's
    file (any city): the same hashing applies, so no address or private name is written."""
    wanted = None if kit_streets is None else {_key(s) for s in kit_streets}
    accounts: dict[str, str] = {}
    for row in _rows(source, ACCOUNTS_FILE):
        if wanted is not None:
            city = _col(row, CITY).upper()
            if city and city != HOUSTON:
                continue
        street = _col(row, STREET)
        if not street:
            continue
        key = _key(street)
        if wanted is None or key in wanted:
            accounts[_col(row, ACCT)] = key
    owners: dict[str, list[str]] = {}
    for row in _rows(source, OWNERS_FILE):
        acct = _col(row, ACCT)
        if acct in accounts:
            owners.setdefault(acct, []).append(_col(row, NAME))
    entries: list[dict[str, object]] = []
    for acct, names in owners.items():
        primary = names[0]
        kind = classify(primary)
        entry: dict[str, object] = {"key": accounts[acct], "kind": kind.value}
        if kind is OwnerKind.COMPANY:
            entry["company"] = primary
        else:
            words = {w for n in names for w in re.findall(r"[A-Z]{2,}", n.upper())}
            entry["name_words"] = sorted(_token_hash(w, salt) for w in words)
        entries.append(entry)
    entries.sort(key=lambda e: str(e["key"]))  # a lookup binary-searches the sorted keys
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        # first line: which salt keyed the name hashes, so a server with another salt says
        # NOT_CHECKED rather than a false NO; and that the rows are sorted by key
        header = {"salt_fingerprint": _salt_fingerprint(salt), "sorted": True}
        fh.write(json.dumps(header) + "\n")
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return len(entries)


def _line_start_at_or_after(fh: BinaryIO, pos: int, start: int) -> int:
    if pos <= start:
        return start
    fh.seek(pos - 1)
    fh.readline()  # the rest of the line that holds pos - 1
    return fh.tell()


def _rows_for_key(fh: BinaryIO, key: str, start: int, end: int) -> list[dict]:
    """Every row with this key in a file sorted by key (binary search over byte offsets)."""
    lo, hi = start, end
    while lo < hi:
        mid = (lo + hi) // 2
        at = _line_start_at_or_after(fh, mid, start)
        if at >= hi:
            hi = mid
            continue
        fh.seek(at)
        line = fh.readline()
        if json.loads(line).get("key", "") < key:
            lo = at + len(line)
        else:
            hi = at
    found: list[dict] = []
    fh.seek(lo)
    for line in fh:
        row = json.loads(line)
        if row.get("key") != key:
            break
        found.append(row)
    return found


def _read_subset(subset: Path, keys: set[str]) -> tuple[str | None, bool, list[dict]]:
    """The salt fingerprint, whether the file was readable, and the rows for these keys."""
    try:
        with subset.open("rb") as fh:
            header = json.loads(fh.readline())
            if header.get("sorted") is True:
                start = fh.tell()
                end = subset.stat().st_size
                found = [row for key in keys for row in _rows_for_key(fh, key, start, end)]
                return header.get("salt_fingerprint"), True, found
            rows = [header, *(json.loads(line) for line in fh)]  # an older, unsorted file
    except (OSError, ValueError):
        return None, False, []
    fingerprint = next((r.get("salt_fingerprint") for r in rows if "salt_fingerprint" in r), None)
    return fingerprint, True, [r for r in rows if r.get("key") in keys]


def _poster_name(text: str) -> tuple[str, str, bool] | None:
    """The poster's own name: only 'my name is' or a signature at the end, never a bare
    "I'm" / "this is" (which read 'I'm Relocating For Work' as a name). The flag says it came
    from a signature, which can be a slogan ('- No Smoking') and so may never give NO."""
    for m, from_signature in (
        (_MY_NAME.search(text), False),
        (_SIGNATURE.search(text.strip()), True),
    ):
        if m and not {m.group(1).upper(), m.group(2).upper()} & _NOT_NAMES:
            return m.group(1), m.group(2), from_signature
    return None


def _street_windows(text: str) -> Iterator[str]:
    """Every run of 2 to 6 words starting with a house number: the street, if there is one."""
    words = normalize_address(text).split()
    for i, w in enumerate(words):
        if w.isdigit():
            for n in range(2, 7):
                if i + n <= len(words):
                    yield " ".join(words[i : i + n])


def _known_company(on_roll: str, known: Iterable[str]) -> str | None:
    """The name of a company we already know that is the owner on the roll, or None.

    Known means a row in the published-rule table (by its name or a verified other name) or a
    name in `known` (offices and brokerages on record in the kit), matched as `same_company`
    reads names. The known entry's own name is returned, never the roll's string, so a name
    that only the county roll holds never leaves here (conductor ruling, round 5 on #160).
    """
    from snapback.agent.rules import published
    from snapback.agent.rules.contact import same_company
    from snapback.agent.rules.owner import published_rule

    if not on_roll:
        return None
    row = published_rule(on_roll, published.PUBLISHED_RULES)
    if row is not None:
        return row.company
    for name in list(known)[:50]:
        if isinstance(name, str) and name.strip() and same_company(name, on_roll):
            return " ".join(name.split())
    return None


def owner(
    listing_text: str,
    subset: Path,
    salt: str,
    known: Iterable[str] = (),
    poster_company: str | None = None,
) -> OwnerResult | None:
    if not subset.is_file():
        return None
    text = listing_text[:_MAX_TEXT]
    keys = {hashlib.sha256(w.encode()).hexdigest() for w in _street_windows(text)}
    fingerprint, readable, found = _read_subset(subset, keys)
    if not readable:
        return None
    if len(found) != 1:
        return None  # no match, or two accounts / two kit streets: never pick one at random
    entry = found[0]
    if entry.get("kind") == OwnerKind.COMPANY.value:
        on_roll = (entry.get("company") or "").strip()
        name = _known_company(on_roll, known)
        if name is not None:
            return OwnerResult(kind=OwnerKind.COMPANY, company=name, company_known=True)
        # any other company is "a company owner": its name is never sent. The company the
        # poster names is compared with the roll here, where the name is, as for a person
        # (round 6 on #160), so "I am the owner, managed by <another company>" still holds.
        from snapback.agent.rules.owner import company_match

        matches = company_match(poster_company, on_roll) if on_roll else OwnerMatch.NOT_CHECKED
        return OwnerResult(kind=OwnerKind.COMPANY, poster_matches=matches)
    name = _poster_name(text)
    if name is None or fingerprint != _salt_fingerprint(salt):
        # no name to compare, or the lookup was keyed with another salt: never a false NO
        return OwnerResult(kind=OwnerKind.PERSON)
    owned = set(entry.get("name_words") or [])
    first, last = (_token_hash(n, salt) in owned for n in name[:2])
    if first and last:
        matches = OwnerMatch.YES
    elif first or last:
        matches = OwnerMatch.NOT_CHECKED  # a nickname, or a shared last name: not a NO
    elif name[2]:
        matches = OwnerMatch.NOT_CHECKED  # a signature can be a slogan: it never gives NO
    else:
        matches = OwnerMatch.NO
    return OwnerResult(kind=OwnerKind.PERSON, poster_matches=matches)


def lookup_owner(
    listing_text: str, known: Iterable[str] = (), poster_company: str | None = None
) -> OwnerResult | None:
    """The entry point lane A's `KitLookups.owner` calls: the lookup under SNAPBACK_DATA_DIR and
    the shared phone salt (set SNAPBACK_PHONE_SALT so the lookup and the check agree). `known`
    is the kit's offices on record for the home, the companies besides the table we can name."""
    from snapback.agent.rules.contact import phone_salt
    from snapback.safety.paths import resolve_data_dir
    from snapback.settings import get_settings

    subset = resolve_data_dir(get_settings().snapback_data_dir) / SUBSET
    return owner(listing_text, subset, phone_salt(), known, poster_company)


def main(argv: list[str] | None = None) -> None:
    from snapback.adapters.costar_jsonl import DEFAULT_KIT, _find, _first, _iter_jsonl
    from snapback.adapters.costar_residential import RESIDENTIAL_FIELDS, RESIDENTIAL_FILE
    from snapback.agent.rules.contact import phone_salt
    from snapback.safety.paths import resolve_data_dir

    parser = argparse.ArgumentParser(description="HCAD owner subset for the kit Houston houses.")
    parser.add_argument("--hcad", type=Path, required=True, help="Real_acct_owner folder or zip")
    parser.add_argument("--kit", type=Path, default=DEFAULT_KIT)
    parser.add_argument(
        "--all-harris",
        action="store_true",
        help="keep every account in the file, not only the kit's houses (the owner check then "
        "covers any Harris County address)",
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--probe", action="store_true", help="print column names only")
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(probe_columns(args.hcad), indent=2))
        return
    out = resolve_data_dir(args.data) / SUBSET
    if args.all_harris:
        kept = build_subset(args.hcad, None, out, phone_salt())
        print(f"owner subset: {kept} Harris County accounts; written to data/{SUBSET.as_posix()}")
        return
    path = _find(args.kit, RESIDENTIAL_FILE)
    if path is None:
        print(f"kit not found ({RESIDENTIAL_FILE})")
        sys.exit(1)
    streets = [
        s for rec in _iter_jsonl(path)
        if isinstance(s := _first(rec, RESIDENTIAL_FIELDS["street"]), str)
    ]  # fmt: skip
    kept = build_subset(args.hcad, streets, out, phone_salt())
    written = f"data/{SUBSET.as_posix()}"
    print(f"owner subset: {kept} houses of {len(streets)} kit addresses; written to {written}")


if __name__ == "__main__":
    main()

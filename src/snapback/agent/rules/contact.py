"""Contact on record (A7, issue #67): does what the listing says about reaching the poster
fit what the property record holds?

Three comparisons, each a yes/no and nothing more:

- the company the poster named, against the manager on record;
- the phone number in the listing, against the leasing office's;
- a link in the listing, against the building's own website.

None of them proves anything about a person. A match never lifts "Allowed to rent it"
(anyone can type a public name or number), a phone match alone does not even count as
matching the record, and a mismatch holds a case, it does not fail one.

What never leaves this module: a phone number, a hash of one, or the record's web address.
The record keeps the office phone only as a keyed hash (`phone_hash`), the listing's numbers
are hashed the same way to compare, and the result that travels on is a status.
"""

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from snapback.contracts import (
    AuthorityResult,
    AuthorityStatus,
    DataSource,
    LinkDomain,
    PhoneMatch,
    PropertyRecord,
)
from snapback.settings import Settings, get_settings

# Synthetic, for fixtures and tests. A live run uses SNAPBACK_PHONE_SALT, or a salt made for
# this process and kept nowhere.
FIXTURE_PHONE_SALT = "fx-phone-salt"
_PROCESS_SALT = secrets.token_hex(16)

MAX_PHONES = 10
MAX_MARKETERS = 20
MAX_LINKS = 20
MAX_HOST = 253
MAX_LABEL = 63
MIN_SITE_NAME = 5  # shorter names are too common to call anything a lookalike of them

# Sites many buildings share. A record that points at one gives nothing to imitate, and a
# link to one says nothing about the poster.
SHARED_HOSTS = frozenset(
    {
        "apartments.com", "zillow.com", "trulia.com", "homes.com", "realtor.com", "rent.com",
        "hotpads.com", "redfin.com", "craigslist.org", "facebook.com", "instagram.com",
        "google.com", "goo.gl", "bit.ly", "linktr.ee", "youtube.com", "docusign.com",
        "docusign.net", "apartmentguide.com", "rentcafe.com", "zumper.com", "padmapper.com",
        "apartmentlist.com", "loopnet.com", "airbnb.com", "vrbo.com",
    }
)  # fmt: skip
_TWO_PART_ENDINGS = frozenset({"co", "com", "org", "net", "gov", "ac", "edu"})

_COMPANY_WORD = re.compile(r"[a-z0-9&.']{1,40}")
_COMPANY_NOISE = frozenset(
    {"llc", "inc", "co", "corp", "corporation", "company", "ltd", "lp", "llp", "the"}
)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{0,10}://")

# Letters that look like other letters. Enough for the common tricks; not a full table.
_LOOKS_LIKE = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i",
        "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ո": "n", "ӏ": "l", "ı": "i", "ɩ": "i",
        "0": "o", "1": "l", "3": "e", "5": "s", "$": "s",
    }
)  # fmt: skip


class Claims(Protocol):
    """What the listing says about reaching the poster (`intake.fields.ContactClaims`)."""

    company: str | None
    phones: list[str]
    links: list[str]


# --- phone ---------------------------------------------------------------------------------


def phone_salt(settings: Settings | None = None) -> str:
    """The salt both lanes hash phones with. Lane D calls this when it reads the record.

    With no SNAPBACK_PHONE_SALT set, a live run gets a salt that lasts as long as the process,
    so the record must be hashed in the process that runs the check. To keep hashes on disk,
    a human sets SNAPBACK_PHONE_SALT.
    """
    settings = settings or get_settings()
    if settings.snapback_phone_salt is not None:
        return settings.snapback_phone_salt.get_secret_value()
    if settings.snapback_data_source is DataSource.FIXTURE:
        return FIXTURE_PHONE_SALT
    return _PROCESS_SALT


def phone_hash(number: str, salt: str) -> str | None:
    """A keyed hash of a ten-digit phone number, or None if `number` is not one.

    HMAC-SHA256 over the digits (a leading 1 is dropped), so the same number written two ways
    gives one hash, and the hash cannot be turned back into the number without the salt.
    """
    digits = "".join(ch for ch in number[:64] if ch in "0123456789")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return hmac.new(salt.encode(), digits.encode(), hashlib.sha256).hexdigest()


def check_phone(phones: Sequence[str], record: PropertyRecord | None, salt: str) -> PhoneMatch:
    on_record = record.site_phone_hash if record is not None else None
    listed = {phone_hash(number, salt) for number in phones[:MAX_PHONES]} - {None}
    if not on_record or not listed:
        return PhoneMatch.NOT_CHECKED
    # Every number in the ad must be the office's: one matching number among others is not
    # the office itself advertising (review round 1, H).
    return PhoneMatch.YES if listed == {on_record} else PhoneMatch.NO


# --- company -------------------------------------------------------------------------------


def _company_words(name: str) -> list[str]:
    words = (word.replace(".", "").replace("'", "") for word in _COMPANY_WORD.findall(name.lower()))
    return [word for word in words if word and word not in _COMPANY_NOISE]


def same_company(said: str | None, on_record: str | None) -> bool | None:
    """Is the company the poster named the manager on record? None when either is missing.

    "Fixture Living" and "Fixture Living LLC" are the same; so is a shorter form that starts
    the same way ("Fixture"). A name that merely shares a later word ("Living") is not.
    """
    if not said or not on_record:
        return None
    ours, theirs = _company_words(said[:200]), _company_words(on_record[:200])
    if not ours or not theirs:
        return None
    short, long = sorted((ours, theirs), key=len)
    return short[0] == long[0] and all(word in long for word in short)


# --- links ---------------------------------------------------------------------------------


def host_of(link: str) -> str | None:
    """The part of a link that says where it goes, lower-cased, without port or "www.".

    A name before an "@" is kept ("real.example@other.example"): browsers ignore it, which is
    exactly why it is used to dress a link up.
    """
    text = _SCHEME.sub("", link.strip().lower()[: MAX_HOST * 2])
    for stop in "/?#":
        text = text.split(stop, 1)[0]
    before, at, where = text.rpartition("@")
    host = where.split(":", 1)[0].strip(".").removeprefix("www.")
    if not host:
        return None
    return f"{before}{at}{host}"[:MAX_HOST]


def _labels(host: str) -> list[str]:
    return [label for label in host.split(".") if label]


def _site_name(host: str) -> str:
    """The label a person reads as the site's name: "oakcourt" in "www.oakcourt.co.uk"."""
    labels = _labels(host)
    if len(labels) >= 3 and labels[-2] in _TWO_PART_ENDINGS and len(labels[-1]) == 2:
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else labels[0]


def _registrable(host: str) -> str:
    labels = _labels(host)
    if len(labels) >= 3 and labels[-2] in _TWO_PART_ENDINGS and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _decoded(label: str) -> str:
    """A punycode label as the letters a browser would show."""
    if not label.startswith("xn--"):
        return label
    try:
        return label[4:].encode("ascii").decode("punycode")
    except (UnicodeError, ValueError):
        return label


def _skeleton(text: str) -> str:
    """Letters and digits only, with accents dropped and look-alike letters folded."""
    plain = unicodedata.normalize("NFKD", text[:MAX_HOST]).lower().translate(_LOOKS_LIKE)
    return "".join(ch for ch in plain if ch.isalnum() and not unicodedata.combining(ch))


def _distance(a: str, b: str) -> int:
    """Edits to turn `a` into `b`: add, drop, change, or swap two neighbours. Short strings."""
    a, b = a[:MAX_LABEL], b[:MAX_LABEL]
    two_back: list[int] = []
    one_back = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        row = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            best = min(one_back[j] + 1, row[j - 1] + 1, one_back[j - 1] + cost)
            if i > 1 and j > 1 and char_a == b[j - 2] and a[i - 2] == char_b:
                best = min(best, two_back[j - 2] + 1)
            row.append(best)
        two_back, one_back = one_back, row
    return one_back[-1]


def _compare(host: str, record_host: str) -> LinkDomain:
    name_before_at, _, where = host.rpartition("@")
    if where == record_host or where.endswith(f".{record_host}"):
        return LinkDomain.MATCHES

    name = _skeleton(_site_name(record_host))
    if _registrable(record_host) in SHARED_HOSTS or len(name) < MIN_SITE_NAME:
        return LinkDomain.OTHER
    if name_before_at and name in _skeleton(name_before_at):
        return LinkDomain.LOOKALIKE
    if _registrable(where) in SHARED_HOSTS:
        return LinkDomain.OTHER

    allowed = 1 if len(name) < 8 else 2
    for label in _labels(where):
        shown = _decoded(label)
        whole = _skeleton(shown)
        # The same name with another ending, or with extra words around it.
        if name in whole:
            return LinkDomain.LOOKALIKE
        # A typo, a swapped pair, a look-alike letter: in the whole label or one word of it.
        for part in (whole, *(_skeleton(word) for word in shown.split("-"))):
            if abs(len(part) - len(name)) <= allowed and _distance(part, name) <= allowed:
                return LinkDomain.LOOKALIKE
    return LinkDomain.OTHER


def _sender_domains(emails: Sequence[str]) -> list[str]:
    """The site each sender address sits on ("payment@fixtureliving.co" -> "fixtureliving.co").

    Only the part after the "@" is read. The part before it is the sender's own choice of
    name, and a small landlord who writes from a personal mailbox is not imitating anyone.
    """
    domains = []
    for email in emails[:MAX_LINKS]:
        _, at, domain = email[: MAX_HOST * 2].rpartition("@")
        host = host_of(domain) if at else None
        if host and "@" not in host:
            domains.append(host)
    return domains


def check_link(links: Sequence[str], website: str | None, emails: Sequence[str] = ()) -> LinkDomain:
    """The listing's links and sender addresses against the building's own site.

    A lookalike outweighs the rest. A bare address ("name@host") is read by its host, the
    same way a link is: the CoStar scam page's first example is a mail from a lookalike
    address posing as the platform.
    """
    record_host = host_of(website) if website else None
    hosts = [host for host in (host_of(link) for link in links[:MAX_LINKS]) if host]
    hosts += _sender_domains(emails)
    if not record_host or "@" in record_host or not hosts:
        return LinkDomain.NOT_CHECKED
    found = {_compare(host, record_host) for host in hosts}
    for status in (LinkDomain.LOOKALIKE, LinkDomain.MATCHES):
        if status in found:
            return status
    return LinkDomain.OTHER


# --- all three -----------------------------------------------------------------------------


def check_authority(
    claims: Claims,
    record: PropertyRecord | None,
    salt: str,
    marketers: Sequence[str] = (),
) -> AuthorityResult:
    """Compare what the listing says about the poster with the record. Yes/no only.

    `marketers` are other company names on record that may market the home: the listing
    brokerage or office (ruling, Sat 01:20). Naming any of them matches, as naming the
    manager does.

    A home that is for sale usually has no property record at all (A15, #132). The listing
    brokerages are still on record, from the for-sale lookup, so they are compared even when
    `record` is None. With neither a record nor a marketer there is nothing to compare with.

    The status says whether the poster matches the contact on record, and only the company
    they named decides it. A phone match alone never does (XO ruling on #87): anyone can copy
    the office's public number into a listing. The phone and link results travel beside the
    status as supporting yes/no lines. With no record there is no office phone and no
    website to compare with, so those two stay "not checked".
    """
    manager = record.manager_company if record is not None else None
    on_record = [name for name in (manager, *marketers[:MAX_MARKETERS]) if name and name.strip()]
    answers = [same_company(claims.company, name) for name in on_record]
    company = True if any(answers) else (False if False in answers else None)
    if company is None:
        status = AuthorityStatus.UNKNOWN
    else:
        status = AuthorityStatus.MATCHES_RECORD if company else AuthorityStatus.MISMATCH

    if record is None:
        # Who to call when the poster named a brokerage on record: that brokerage. A company,
        # from the record, never what the poster typed. Nobody is named when they named none.
        matched = next((name for name, same in zip(on_record, answers, strict=True) if same), None)
        return AuthorityResult(
            status=status,
            manager_on_record=matched,
            poster_said=claims.company,
            # True when there was a brokerage to compare with. The card and the reasons then
            # speak of the listing brokerage, never of a manager or a leasing office.
            brokerage_only=bool(on_record),
        )

    return AuthorityResult(
        status=status,
        manager_on_record=record.manager_company,
        poster_said=claims.company,
        office_phone_match=check_phone(claims.phones, record, salt),
        link_domain=check_link(claims.links, record.website_host, getattr(claims, "emails", ())),
    )

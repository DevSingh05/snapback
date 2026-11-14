"""Which website domain is the office's own, and whether an address is at it.

The domain comes from CoStar's record and from nowhere else: `official_domain` takes the
record and nothing more, so a domain printed in an ad has no way in. Free mail, listing and
social platforms, and site builders are never an office's own domain, and a host with
punycode or non-ASCII letters (a lookalike of a real name) is rejected outright.

There is no public-suffix library in the dependencies, so the registrable domain is the last
two labels, or the last three under the small list of two-part endings below. Anything this
list does not know falls back to the last two labels, which is stricter, never looser: a
host under an unknown two-part ending reads as the ending itself and is refused by the
platform and shape checks or matched only exactly.
"""

import re

# Two-part country endings where the registrable domain has three labels ("oakcourt.co.uk").
TWO_PART_ENDINGS = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "me.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "co.za",
        "co.in",
        "co.jp",
        "co.kr",
        "co.il",
        "com.mx",
        "com.br",
        "com.ar",
        "com.co",
        "com.sg",
        "com.hk",
        "com.tr",
        "com.cn",
        # Private endings that sell names under a country label (evil.us.com is not us.com).
        "us.com",
        "uk.com",
        "eu.com",
        "gb.com",
        "co.com",
        "uk.net",
        "gb.net",
        "se.net",
        "za.com",
        "br.com",
        "cn.com",
        "de.com",
        "jpn.com",
        "ru.com",
        "sa.com",
        "qc.com",
        "kr.com",
        "in.net",
    }
)
# A label that is part of an ending, not a name. "oakcourt.co.xx" under an ending we do not
# know would read as the name "co" on "xx", so such a host is refused rather than guessed.
GENERIC_LABELS = frozenset({"com", "co", "net", "org", "gov", "edu", "ac"})

# Free mail: anyone can open one, so it proves nothing about an office.
FREE_MAIL = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "ymail.com",
        "rocketmail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "aol.com",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "fastmail.com",
        "hey.com",
        "tutanota.com",
        "comcast.net",
        "att.net",
        "verizon.net",
        "sbcglobal.net",
        "cox.net",
        "charter.net",
        "earthlink.net",
    }
)
# The same providers under other country endings (yahoo.co.uk, hotmail.fr, outlook.de).
FREE_MAIL_NAMES = frozenset({"gmail", "yahoo", "hotmail", "outlook", "icloud", "proton", "aol"})

# Where listings, social pages and free sites live. A page there is not the office's domain.
PLATFORMS = frozenset(
    {
        "zillow.com",
        "apartments.com",
        "costar.com",
        "trulia.com",
        "realtor.com",
        "redfin.com",
        "homes.com",
        "hotpads.com",
        "rent.com",
        "rentals.com",
        "rentcafe.com",
        "zumper.com",
        "padmapper.com",
        "apartmentlist.com",
        "apartmentguide.com",
        "forrent.com",
        "loopnet.com",
        "craigslist.org",
        "offerup.com",
        "facebook.com",
        "fb.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "tiktok.com",
        "youtube.com",
        "nextdoor.com",
        "airbnb.com",
        "vrbo.com",
        "booking.com",
        "hilton.com",
        "marriott.com",
        "google.com",
        "linktr.ee",
        "wix.com",
        "wixsite.com",
        "godaddysites.com",
        "weebly.com",
        "squarespace.com",
        "wordpress.com",
        "blogspot.com",
        "business.site",
        "carrd.co",
        "github.io",
        "netlify.app",
        "vercel.app",
        "herokuapp.com",
        "pages.dev",
        # Property-management software vendors host many unrelated offices' sites.
        "appfolio.com",
        "prospectportal.com",
        "rentmanager.com",
        "managebuilding.com",
        "tenantturner.com",
        "rentcafewebsite.com",
        "securecafe.com",
        "entrata.com",
        "realpage.com",
        "rently.com",
        "buildium.com",
        "showmojo.com",
    }
)

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD = re.compile(r"^[a-z]{2,24}$")
MAX_HOST = 253


def registrable_domain(host: str | None) -> str | None:
    """The domain a person registers ("oakcourt.example") from a host, or None if the host is
    malformed, punycode, non-ASCII, an address of numbers, or only a public ending."""
    if not isinstance(host, str):
        return None
    text = host.lower()
    if not text or len(text) > MAX_HOST or not text.isascii():
        return None
    labels = text.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(label) for label in labels):
        return None
    if any(label.startswith("xn--") for label in labels) or not _TLD.fullmatch(labels[-1]):
        return None
    known_ending = ".".join(labels[-2:]) in TWO_PART_ENDINGS
    if not known_ending and labels[-2] in GENERIC_LABELS:
        return None  # "x.co.xx": an ending we do not know; never guess a name from it
    keep = 3 if known_ending else 2
    if len(labels) < keep:
        return None
    return ".".join(labels[-keep:])


def _never_an_office(domain: str) -> bool:
    if domain in FREE_MAIL or domain in PLATFORMS:
        return True
    labels = domain.split(".")
    return labels[-2] in FREE_MAIL_NAMES or (
        len(labels) >= 3
        and ".".join(labels[-2:]) in TWO_PART_ENDINGS
        and labels[-3] in FREE_MAIL_NAMES
    )


def official_domain(record: object | None) -> str | None:
    """The office's own website domain, from CoStar's record only.

    Reads the record's `website_host` (the building's own site, host only) and nothing else.
    None when the record has no website, or the host is free mail, a platform, or not a
    clean registrable domain. A house with no website on record is None: that is the common
    case, and the answer is to call the office on a number the renter looks up.
    """
    host = getattr(record, "website_host", None)
    domain = registrable_domain(host)
    if domain is None or _never_an_office(domain):
        return None
    return domain


_ADDRESS = re.compile(r"^([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64})@([A-Za-z0-9.-]{1,253})$")


def accepts_address(address: str | None, official: str | None) -> bool:
    """Is this email address at exactly the office's official domain (decision 183)?

    Any local part is fine: we never learn who the office's people are. The domain is
    compared exactly, after lower-casing: a subdomain, punycode and non-ASCII are refused.
    """
    if official is None or not isinstance(address, str):
        return False
    found = _ADDRESS.fullmatch(address)
    if found is None:
        return False
    domain = found.group(2).lower()
    return domain == official and registrable_domain(domain) == official

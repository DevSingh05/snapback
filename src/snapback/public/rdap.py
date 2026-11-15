"""RDAP domain age: how long ago a link's domain was registered.

RDAP is the registries' free, keyless lookup (rdap.org routes to the right registry). A domain
registered less than `snapback_new_domain_days` ago, in a link the ad sends, is the
`link.new_domain` rule (a red flag that holds, never DONT_PAY alone). An old domain says
nothing good or bad.
An RDAP error, a domain with no registration date, or a timeout is "not checked", never a flag.
"""

import re
from datetime import UTC, date, datetime

from snapback.contracts import DomainCheck, PublicStatus, RuleCategory, RuleHit
from snapback.public.fetch import Fetcher

SOURCE_NAME = "RDAP"
RULE_ID = "link.new_domain"
URL = "https://rdap.org/domain/"
_LINK = re.compile(r"https?://([^\s/\"'<>?#:]{1,253})", re.I)
_HOST = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)
# Hosts that are platforms, not a poster's own domain: their age says nothing about the poster.
_COMMON = (
    "google.com", "docs.google.com", "forms.gle", "facebook.com", "fb.com", "instagram.com",
    "craigslist.org", "zillow.com", "apartments.com", "trulia.com", "realtor.com", "hotpads.com",
    "paypal.com", "paypal.me", "venmo.com", "cash.app", "docusign.com", "docusign.net",
    "youtube.com", "youtu.be", "bit.ly", "tinyurl.com", "t.co", "wa.me",
)  # fmt: skip


def registrable(host: str) -> str:
    """The last two labels (or three for a two-letter country code with a short second label)."""
    labels = host.lower().rstrip(".").split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in {"co", "com", "org", "net"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def link_host(text: str) -> str | None:
    """The first link's domain in the ad that is not a well-known platform, or None."""
    for found in _LINK.finditer(text or ""):
        host = registrable(found.group(1))
        if not _HOST.fullmatch(host):
            continue
        if any(host == known or host.endswith("." + known) for known in _COMMON):
            continue
        return host
    return None


def _registered_on(body: dict) -> date | None:
    for event in body.get("events") or []:
        if event.get("eventAction") == "registration":
            try:
                stamp = str(event["eventDate"]).replace("Z", "+00:00")
                return datetime.fromisoformat(stamp).astimezone(UTC).date()
            except (KeyError, ValueError):
                return None
    return None


def check(host: str, fetcher: Fetcher, *, today: date, timeout: float = 2.0) -> DomainCheck:
    """The domain's registration date and age in days; NOT_CHECKED when RDAP cannot say."""
    body = fetcher.get("rdap", host.lower(), f"{URL}{host.lower()}", timeout)
    registered = _registered_on(body) if body else None
    if registered is None:
        return DomainCheck(host=host, status=PublicStatus.NOT_CHECKED, source=fetcher.source)
    return DomainCheck(
        host=host,
        status=PublicStatus.FOUND,
        registered_on=registered,
        age_days=max((today - registered).days, 0),
        source=fetcher.source,
    )


def rule_hit(found: DomainCheck, max_days: int) -> RuleHit | None:
    """`link.new_domain`, only when RDAP answered and the domain is younger than `max_days`."""
    if found.status is not PublicStatus.FOUND or found.age_days is None:
        return None
    if found.age_days >= max_days:
        return None
    return RuleHit(rule_id=RULE_ID, category=RuleCategory.LINK, red_flag=True)

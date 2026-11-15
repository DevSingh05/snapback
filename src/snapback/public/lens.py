"""Google Lens through SerpApi: has the ad's own photo appeared on a for-sale listing page?

This is the fallback for a home CoStar has no 3D scan of (CoStar stays primary: its scan places
the photos). A photo that also sits on a Zillow, Redfin, Realtor.com, Homes.com or HAR page for
the home is the classic hijack signature, and feeds the existing `for_sale_flag` (HOLD, never
DONT_PAY on its own), named "Google Lens via SerpApi".

What is sent: only the ad's own public photo links found in the ad text (at most 2), never an
uploaded file. The key is `SERPAPI_API_KEY`, sent as the `api_key` parameter SerpApi's docs
specify; it is never logged or put in a result. A missing key, a timeout or any error is "not
checked" (None). Free plan: 250 searches a month, so the caller caps photos per case.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

from snapback.contracts import ForSaleMatch, ForSaleStatus
from snapback.public.fetch import Fetcher

SOURCE_NAME = "Google Lens via SerpApi"
URL = "https://serpapi.com/search.json"
MAX_PHOTOS = 2
_IMAGE = re.compile(
    r"https?://[^\s\"'<>]{1,300}?(?:\.(?:jpe?g|png|webp)(?:\?[^\s\"'<>]{0,100})?|/images?/[^\s\"'<>]{1,200})",
    re.I,
)
# Pages where a home is listed for sale. A page whose address says rent is not one.
LISTING_HOSTS = (
    "zillow.com", "redfin.com", "realtor.com", "homes.com", "har.com", "trulia.com",
    "movoto.com", "compass.com", "coldwellbanker.com", "century21.com", "remax.com", "kw.com",
)  # fmt: skip
_RENTAL = re.compile(r"rent|lease|apartment", re.I)


def photo_urls(text: str) -> list[str]:
    """The ad's own public photo links, in order, at most `MAX_PHOTOS`, no duplicates."""
    found = dict.fromkeys(m.group(0) for m in _IMAGE.finditer(text or ""))
    return list(found)[:MAX_PHOTOS]


def _host(link: str) -> str:
    return (urlparse(link).hostname or "").lower().removeprefix("www.")


def listing_host_in(body: dict | None) -> str | None:
    """The first visual match that is a for-sale listing page, as its host. None if none."""
    matches = body.get("visual_matches") if isinstance(body, dict) else None
    for match in matches or []:
        link = match.get("link") if isinstance(match, dict) else None
        if not isinstance(link, str):
            continue
        host = _host(link)
        listed = any(host == known or host.endswith("." + known) for known in LISTING_HOSTS)
        if listed and not _RENTAL.search(urlparse(link).path):
            return host
    return None


def check(
    text: str, fetcher: Fetcher, api_key: str | None, timeout: float = 4.0
) -> ForSaleMatch | None:
    """A for-sale match when a photo of the ad is on a listing page, else None (no match, no
    photo link, no key or any failure: nothing was found, so nothing is claimed)."""
    photos = photo_urls(text)
    if not photos or not api_key:
        return None

    def one(photo: str) -> str | None:
        url = f"{URL}?engine=google_lens&url={quote(photo, safe='')}&api_key={api_key}"
        return listing_host_in(fetcher.get("lens", photo, url, timeout))

    with ThreadPoolExecutor(max_workers=MAX_PHOTOS, thread_name_prefix="lens") as pool:
        hosts = list(pool.map(one, photos))
    host = next((h for h in hosts if h), None)
    if host is None:
        return None
    return ForSaleMatch(status=ForSaleStatus.ACTIVE, site=host, source_name=SOURCE_NAME)

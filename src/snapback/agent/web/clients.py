"""W1: the three web services, each a few HTTP calls. Every call takes an `httpx.Client`, so tests
pass one with a `MockTransport` that answers from recorded JSON and nothing reaches the network.

Keys come from Settings as SecretStr and go only into request headers; they are never logged,
returned or put in an address. Each function raises `WebError` with a short reason of our own
words (never the service's body, which can echo the request) when the service fails.
"""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import quote, quote_plus

import httpx
from pydantic import SecretStr

BRIGHTDATA_URL = "https://api.brightdata.com/request"
APIFY_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
BROWSER_USE_URL = "https://api.browser-use.com/api/v4"
MAX_BODY = 2_000_000


class WebError(Exception):
    """A service did not give a usable answer. The message is ours and holds no secret."""


def _ok(res: httpx.Response, what: str) -> httpx.Response:
    if res.status_code >= 400:
        raise WebError(f"{what} answered {res.status_code}")
    if len(res.content) > MAX_BODY:
        raise WebError(f"{what} answer too large")
    return res


# --- Bright Data ------------------------------------------------------------------------------


def unlock(http: httpx.Client, token: SecretStr, zone: str, url: str, timeout: float) -> str:
    """A page through Bright Data's Web Unlocker: the raw HTML."""
    res = http.post(
        BRIGHTDATA_URL,
        headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        json={"zone": zone, "url": url, "format": "raw"},
        timeout=timeout,
    )
    return _ok(res, "Bright Data").text


def serp(
    http: httpx.Client, token: SecretStr, zone: str, query: str, timeout: float
) -> dict[str, Any]:
    """Google results through Bright Data's SERP API, parsed (`brd_json=1`): {"organic": [...]}."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=20&brd_json=1"
    res = http.post(
        BRIGHTDATA_URL,
        headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        json={"zone": zone, "url": url, "format": "raw"},
        timeout=timeout,
    )
    try:
        data = _ok(res, "Bright Data search").json()
    except ValueError as e:
        raise WebError("Bright Data search answer was not JSON") from e
    if not isinstance(data, dict):
        raise WebError("Bright Data search answer had no results")
    return data


# --- free stand-ins (no Bright Data zones) -----------------------------------------------------

APIFY_SEARCH_ACTOR = "apify~google-search-scraper"
PAGE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SNAPBACK listing check)"}
MAX_HOPS = 3


def fetch_page(
    http: httpx.Client, url: str, timeout: float, may_open: Callable[[str], bool]
) -> str:
    """A page fetched directly, following at most 3 redirects, each one checked with
    `may_open` first, so a redirect can never take us to a host we must not open."""
    for _ in range(MAX_HOPS + 1):
        if not may_open(url):
            raise WebError("the page redirected somewhere we do not open")
        res = http.get(url, headers=PAGE_HEADERS, timeout=timeout, follow_redirects=False)
        if res.is_redirect and res.headers.get("location"):
            url = str(res.url.join(res.headers["location"]))
            continue
        return _ok(res, "The building's site").text
    raise WebError("too many redirects")


def apify_search(
    http: httpx.Client, token: SecretStr, query: str, timeout: float
) -> dict[str, Any]:
    """Google results through Apify's search actor, shaped like Bright Data's parsed answer
    ({"organic": [{"link", "title", "description"}]}) so the same reader handles both."""
    pages = run_actor(
        http,
        token,
        APIFY_SEARCH_ACTOR,
        {"queries": query, "maxPagesPerQuery": 1, "resultsPerPage": 20, "countryCode": "us"},
        max_items=None,  # one query, one page: the actor returns one item
        timeout=timeout,
    )
    organic: list[dict[str, Any]] = []
    for page in pages:
        for row in page.get("organicResults") or []:
            if isinstance(row, Mapping) and isinstance(row.get("url"), str):
                organic.append(
                    {
                        "link": row["url"],
                        "title": row.get("title") or "",
                        "description": row.get("description") or "",
                    }
                )
    return {"organic": organic}


# --- Apify ------------------------------------------------------------------------------------


def run_actor(
    http: httpx.Client,
    token: SecretStr,
    actor: str,
    actor_input: Mapping[str, Any],
    *,
    max_items: int | None,
    timeout: float,
) -> list[dict[str, Any]]:
    """Run an Apify actor and wait for its dataset items (`run-sync-get-dataset-items`).
    `max_items` None sends no item cap: on a pay-per-event actor a small `maxItems` sets a
    cost cap under Apify's $0.50 minimum and the run is refused (400)."""
    params: dict[str, Any] = {"timeout": int(timeout), "format": "json", "clean": 1}
    if max_items is not None:
        params["maxItems"] = max_items
    res = http.post(
        APIFY_URL.format(actor=actor),
        headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        params=params,
        json=dict(actor_input),
        timeout=timeout + 5,
    )
    if res.status_code == 408:
        raise WebError("Apify run ran out of time")
    try:
        items = _ok(res, "Apify").json()
    except ValueError as e:
        raise WebError("Apify answer was not JSON") from e
    if not isinstance(items, list):
        raise WebError("Apify answer was not a list")
    kept = [item for item in items if isinstance(item, dict)]
    return kept[:max_items] if max_items is not None else kept


ZILLOW_BOX = 0.03  # degrees each way from the centre: a few kilometres


def zillow_rentals_url(center: tuple[float, float], beds: int | None) -> str:
    """A Zillow for-rent search page around a point. The actor needs `searchQueryState` with
    map bounds in the address (a plain /city/rentals/ page gives "No searchQueryState")."""
    lat, lon = round(center[0], 2), round(center[1], 2)
    flags = ("fsba", "fsbo", "nc", "cmsn", "auc", "fore")
    filters: dict[str, Any] = {"fr": {"value": True}, **{k: {"value": False} for k in flags}}
    if beds is not None:
        filters["beds"] = {"min": beds, "max": beds}
    state = {
        "pagination": {},
        "isMapVisible": True,
        "isListVisible": True,
        "mapBounds": {
            "north": round(lat + ZILLOW_BOX, 4),
            "south": round(lat - ZILLOW_BOX, 4),
            "east": round(lon + ZILLOW_BOX, 4),
            "west": round(lon - ZILLOW_BOX, 4),
        },
        "filterState": filters,
    }
    query = quote(json.dumps(state, separators=(",", ":")))
    return f"https://www.zillow.com/homes/for_rent/?searchQueryState={query}"


# --- Browser Use ------------------------------------------------------------------------------

LINK_TASK = (
    "Open {link}. If the page has a button or link to apply, rent, reserve or pay a deposit, "
    "click it once and wait for the next page. Do not type anything into any form and do not "
    "pay. If any page you reach is on facebook.com, fb.com or apartments.com, stop at once and "
    "report that address without doing anything on it. Report the final page address, and "
    "whether that page asks for a payment, deposit or card details before a viewing."
)
LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "final_url": {"type": "string"},
        "asks_payment": {"type": "boolean"},
    },
    "required": ["final_url", "asks_payment"],
}
DONE = {"completed"}
STOPPED = {"failed", "cancelled"}


def open_link(
    http: httpx.Client,
    key: SecretStr,
    link: str,
    *,
    max_cost_usd: float,
    timeout: float,
    poll_s: float = 1.0,
    clock=time.monotonic,
    sleep=time.sleep,
) -> tuple[str | None, bool | None, float | None]:
    """Open the ad's link in Browser Use's cloud browser. Returns (final_url, asks_payment,
    cost in dollars). The run is cancelled if it is still going when the time is up."""
    headers = {"X-Browser-Use-API-Key": key.get_secret_value()}
    made = http.post(
        f"{BROWSER_USE_URL}/runs",
        headers=headers,
        json={
            "task": LINK_TASK.format(link=link),
            "outputSchema": LINK_SCHEMA,
            "maxCostUsd": max_cost_usd,
        },
        timeout=timeout,
    )
    run_id = _ok(made, "Browser Use").json().get("id")
    if not isinstance(run_id, str):
        raise WebError("Browser Use gave no run id")
    end = clock() + timeout
    while True:
        status = (
            _ok(
                http.get(
                    f"{BROWSER_USE_URL}/runs/{run_id}/status", headers=headers, timeout=timeout
                ),
                "Browser Use",
            )
            .json()
            .get("status")
        )
        if status in DONE or status in STOPPED:
            break
        if clock() >= end:
            http.post(f"{BROWSER_USE_URL}/runs/{run_id}/cancel", headers=headers, timeout=5)
            raise TimeoutError("Browser Use run did not finish in time")
        sleep(poll_s)
    run = _ok(
        http.get(f"{BROWSER_USE_URL}/runs/{run_id}", headers=headers, timeout=timeout),
        "Browser Use",
    ).json()
    cost = run.get("totalCostUsd")
    cost = float(cost) if isinstance(cost, int | float | str) and str(cost).strip() else None
    if status in STOPPED:
        raise WebError(f"Browser Use run {status}")
    output = run.get("output")
    if not isinstance(output, Mapping):
        return None, None, cost
    final = output.get("final_url")
    asks = output.get("asks_payment")
    return (
        final if isinstance(final, str) else None,
        asks if isinstance(asks, bool) else None,
        cost,
    )


def first_words(text: str, n: int = 8) -> str | None:
    """A short exact phrase from the ad's own words for a quoted search, or None."""
    words: Sequence[str] = [w for w in text.replace('"', " ").split() if w.isascii()]
    best = max(
        (words[i : i + n] for i in range(0, max(1, len(words) - n + 1))),
        key=lambda chunk: sum(len(w) for w in chunk),
        default=[],
    )
    return " ".join(best) if len(best) >= 5 else None

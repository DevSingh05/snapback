"""W1: run the three web checks in parallel under one shared time limit.

A check whose key is missing, or that has nothing to look at, reads "not checked" at once. A
check still running when the limit passes reads "timed out"; its thread is left to finish on
its own and its answer is dropped. Nothing here can fail the case: every error becomes a
status. Each finished check lands in the trace as one step (when a trace is given).
"""

import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

import httpx

from snapback.agent.web import clients
from snapback.agent.web.facts import (
    CheckStatus,
    ElsewhereCheck,
    LinkCheck,
    SiteCheck,
    WebFacts,
    WebInputs,
    elsewhere_facts,
    link_facts,
    search_hits,
    site_facts,
)
from snapback.contracts import DataSource, TraceKind
from snapback.settings import Settings

MAX_RENTALS = 25  # items asked of each Apify search
# Never opened or fetched, whatever the ad links to (sponsor and platform terms, #8).
NEVER_OPEN = ("facebook.com", "fb.com", "fb.me", "m.me", "apartments.com")
_PLAIN_LINK = re.compile(r"https?://[^\s\"'<>`]+", re.I)


def may_open(link: str | None) -> bool:
    """A link we may hand to a browser or fetch: http(s) only, no whitespace or quotes (it goes
    into an agent's task text), and never a host we must not open."""
    if not link or not _PLAIN_LINK.fullmatch(link) or "\\" in link:
        return False
    try:
        url = httpx.URL(link)
    except (httpx.InvalidURL, ValueError):
        return False
    if url.userinfo:  # "https://x@facebook.com/..." really goes to facebook.com
        return False
    host = url.host.lower().rstrip(".")
    if not host:
        return False
    return not any(host == bad or host.endswith("." + bad) for bad in NEVER_OPEN)


_URL_OR_PHONE = re.compile(r"https?://\S+|\S+@\S+|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


def ad_phrase(text: str | None) -> str | None:
    """A short exact phrase from the ad's own words for a quoted search: no link, no address,
    no phone number in it."""
    if not text:
        return None
    return clients.first_words(_URL_OR_PHONE.sub(" ", text))


def _site(
    inputs: WebInputs, settings: Settings, http: httpx.Client, salt: str, limit: float
) -> SiteCheck:
    token = settings.brightdata_api_token
    url = f"https://{inputs.website_host}/" if inputs.website_host else None
    if url is None or not may_open(url):
        return SiteCheck(host=inputs.website_host)
    if token is not None:
        raw = clients.unlock(http, token, settings.brightdata_unlocker_zone, url, limit)
    elif settings.snapback_web_direct_fetch:
        raw = clients.fetch_page(http, url, limit, may_open)
    else:
        return SiteCheck(host=inputs.website_host)
    return site_facts(raw, inputs, salt)


def _link(inputs: WebInputs, settings: Settings, http: httpx.Client, limit: float) -> LinkCheck:
    key = settings.browser_use_api_key
    if key is None or not may_open(inputs.ad_link):
        return LinkCheck()
    final, asks, cost = clients.open_link(
        http, key, inputs.ad_link, max_cost_usd=settings.browser_use_max_cost_usd, timeout=limit
    )
    found = link_facts(final, asks, inputs.website_host)
    return found.model_copy(update={"cost_usd": cost})


def _elsewhere(
    inputs: WebInputs, settings: Settings, http: httpx.Client, salt: str, limit: float
) -> ElsewhereCheck:
    token, apify = settings.brightdata_api_token, settings.apify_token
    hits = None
    rentals: dict[str, list[dict[str, Any]]] = {}
    if inputs.ad_phrase and (token is not None or apify is not None):
        query = f'"{inputs.ad_phrase}"' + (f" {inputs.city}" if inputs.city else "")
        if token is not None:
            answer = clients.serp(http, token, settings.brightdata_serp_zone, query, limit)
        else:  # no Bright Data zones: the same search through Apify's Google actor
            answer = clients.apify_search(http, apify, query, limit)  # type: ignore[arg-type]
        hits = search_hits(answer, inputs.website_host)
    if apify is not None and inputs.center is not None:
        actors = {
            "zillow": (
                settings.apify_zillow_actor,
                {
                    "searchUrls": [{"url": clients.zillow_rentals_url(inputs.center, inputs.beds)}],
                    "maxItems": MAX_RENTALS,
                },
            ),
            "craigslist": (
                settings.apify_craigslist_actor,
                {"city": inputs.city, "category": "apa", "maxItems": MAX_RENTALS},
            ),
        }
        for name, (actor, actor_input) in actors.items():
            if actor:
                rentals[name] = clients.run_actor(
                    http, apify, actor, actor_input, max_items=MAX_RENTALS, timeout=limit
                )
    if hits is None and not rentals:
        return ElsewhereCheck()
    return elsewhere_facts(hits, rentals, inputs, salt)


def _status_of(error: BaseException) -> CheckStatus:
    timed = isinstance(error, TimeoutError | httpx.TimeoutException)
    return CheckStatus.TIMED_OUT if timed else CheckStatus.FAILED


def run_web_checks(
    inputs: WebInputs,
    settings: Settings,
    *,
    salt: str,
    source: DataSource = DataSource.LIVE,
    http: httpx.Client | None = None,
    on_step: Callable[[str, Any], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> WebFacts:
    """The three checks, side by side, within `settings.snapback_web_limit_s` seconds."""
    limit = settings.snapback_web_limit_s
    client = http or httpx.Client(follow_redirects=True)
    jobs: dict[str, Callable[[], Any]] = {
        "site": lambda: _site(inputs, settings, client, salt, limit),
        "link": lambda: _link(inputs, settings, client, limit),
        "elsewhere": lambda: _elsewhere(inputs, settings, client, salt, limit),
    }
    blank = {"site": SiteCheck, "link": LinkCheck, "elsewhere": ElsewhereCheck}
    start = clock()
    took: dict[str, int] = {}

    def timed(name: str, job: Callable[[], Any]) -> Any:
        try:
            return job()
        finally:
            took[name] = int((clock() - start) * 1000)

    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="web-check")
    futures: dict[str, Future] = {name: pool.submit(timed, name, job) for name, job in jobs.items()}
    wait(futures.values(), timeout=limit)
    pool.shutdown(wait=False, cancel_futures=True)
    out: dict[str, Any] = {}
    for name, future in futures.items():
        ms = took.get(name, int(limit * 1000))
        if not future.done():
            result = blank[name](status=CheckStatus.TIMED_OUT)
        elif future.exception() is not None:
            result = blank[name](status=_status_of(future.exception()))  # type: ignore[arg-type]
        else:
            result = future.result()
        if result.status is not CheckStatus.NOT_CHECKED and result.ms is None:
            result = result.model_copy(update={"ms": ms})
        out[name] = result
        if on_step is not None:
            on_step(name, result)
    if http is None:
        client.close()
    return WebFacts(source=source, **out)


STEP_WORDS = {
    "site": "Read the building's own site",
    "link": "Opened the ad's link in Browser Use",
    "elsewhere": "Searched for the ad's own words posted elsewhere, and rentals this size nearby",
}


CAP_WORDS = "Web checks skipped: the hourly limit on web checks is reached."


class HourlyCap:
    """At most `n` starts in any rolling hour, across all cases. Thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._starts: list[float] = []
        self._lock = threading.Lock()

    def take(self, n: int) -> bool:
        with self._lock:
            now = self._clock()
            self._starts = [t for t in self._starts if now - t < 3600]
            if len(self._starts) >= n:
                return False
            self._starts.append(now)
            return True


WEB_CAP = HourlyCap()


class WebJob:
    """The web checks running in the background for one case. `facts()` never blocks: it is
    None until all three have finished or timed out. Each finished check emits one trace step."""

    def __init__(self) -> None:
        self._facts: WebFacts | None = None
        self._done = threading.Event()

    def facts(self) -> WebFacts | None:
        return self._facts

    def wait(self, timeout: float) -> WebFacts | None:
        self._done.wait(timeout)
        return self._facts

    def _finish(self, facts: WebFacts | None) -> None:
        self._facts = facts
        self._done.set()


def start_web_checks(
    inputs: WebInputs,
    settings: Settings,
    *,
    salt: str,
    trace: Any = None,
    source: DataSource = DataSource.LIVE,
    http: httpx.Client | None = None,
    cap: HourlyCap | None = None,
) -> WebJob:
    """Start the checks on a daemon thread and return at once, so the text answer is not held
    up. Set `case.web_facts = job.facts` to give the web sub-agent and the notes the result.
    Past `settings.snapback_web_max_per_hour` starts in the last hour, nothing is called and
    every check reads "not checked"."""
    job = WebJob()
    if not (cap or WEB_CAP).take(settings.snapback_web_max_per_hour):
        if trace is not None:
            trace.emit(TraceKind.STATUS, CAP_WORDS, pick="web.cap")
        job._finish(WebFacts(source=source))
        return job

    def step(name: str, result: Any) -> None:
        if trace is None:
            return
        status = result.status.value.replace("_", " ")
        took = f" in {result.ms} ms" if result.ms is not None else ""
        trace.emit(TraceKind.TOOL, f"{STEP_WORDS[name]}: {status}{took}.", pick=f"web.{name}")

    def go() -> None:
        try:
            job._finish(
                run_web_checks(inputs, settings, salt=salt, source=source, http=http, on_step=step)
            )
        except Exception:  # never fails the case
            job._finish(None)

    threading.Thread(target=go, name="web-checks", daemon=True).start()
    return job

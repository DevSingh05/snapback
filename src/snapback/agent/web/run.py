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
    if token is None or not inputs.website_host:
        return SiteCheck(host=inputs.website_host)
    raw = clients.unlock(
        http, token, settings.brightdata_unlocker_zone, f"https://{inputs.website_host}/", limit
    )
    return site_facts(raw, inputs, salt)


def _link(inputs: WebInputs, settings: Settings, http: httpx.Client, limit: float) -> LinkCheck:
    key = settings.browser_use_api_key
    if key is None or not inputs.ad_link:
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
    hits: list[str] | None = None
    rentals: dict[str, list[dict[str, Any]]] = {}
    if token is not None and inputs.ad_phrase:
        query = f'"{inputs.ad_phrase}"' + (f" {inputs.city}" if inputs.city else "")
        answer = clients.serp(http, token, settings.brightdata_serp_zone, query, limit)
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
    "site": "Read the building's own site through Bright Data",
    "link": "Opened the ad's link in Browser Use",
    "elsewhere": "Searched for the same home posted elsewhere (Bright Data search, Apify)",
}


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
) -> WebJob:
    """Start the checks on a daemon thread and return at once, so the text answer is not held
    up. Set `case.web_facts = job.facts` to give the web sub-agent and the notes the result."""
    job = WebJob()

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

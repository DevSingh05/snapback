"""W1 (#11, Vidyut 20:05): the web checks behind the deepagents `web` sub-agent.

Three checks, each one evidence line with source LIVE, all built by code:

1. **The building's own site** (the record's `website_host`): does it list a plan with the ad's
   beds, and is the phone on it the office number on record? Yes or no only: no digits leave.
2. **The ad's link:** opened. A different host that uses the building's name is a lookalike.
3. **The same home elsewhere:** the ad's own first sentence searched as an exact phrase. Counts
   only (how many other listings, how many at a different price), never a name, host or link.

Rules:
- The three run in parallel under one hard time limit (`budget_s`, about 15 s). A check that is
  not done by then is "not checked (time limit)"; a fetch that fails is "not checked".
- Facebook (Marketplace) is never opened: renters paste or forward it.
- These lines are evidence for the trace and the explanation only. `decide()` never reads them.
- The fetcher is an interface: `BrightDataFetcher` live (key in `.env`, never printed),
  `RecordedFetcher` in tests (no network in CI).
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from snapback.agent.rules.contact import phone_hash

Status = Literal["matches", "doesnt_match", "warning", "not_checked"]
Check = Literal["building_site", "ad_link", "elsewhere"]

BUDGET_S = 15.0
NEVER_OPEN = re.compile(r"(^|\.)(facebook\.com|fb\.com|fb\.me|messenger\.com)$", re.I)
_PHONE = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}")
_MONEY = re.compile(r"\$\s?(\d{1,2},?\d{3}|\d{3,5})")


@dataclass(frozen=True)
class WebInputs:
    """What the web checks need, from the record and the ad. No raw phone number of the ad."""

    website_host: str | None
    site_phone_hash: str | None
    salt: str
    building_name: str | None
    ad_hosts: list[str]
    ad_text: str
    ad_rent: int | None
    ad_beds: int | None


@dataclass(frozen=True)
class WebLine:
    check: Check
    status: Status
    text: str  # built by code; never a phone digit, a name of a person or a result's link
    source: Literal["live"] = "live"


@dataclass
class WebReport:
    lines: list[WebLine] = field(default_factory=list)
    seconds: float = 0.0


class Fetcher(Protocol):
    def page(self, url: str) -> str | None: ...

    def search(self, query: str) -> list[dict]: ...


class RecordedFetcher:
    """Pages and searches recorded in a JSON file. The only fetcher tests use."""

    def __init__(self, path: Path) -> None:
        recorded = json.loads(Path(path).read_text(encoding="utf-8"))
        self._pages: dict[str, str] = recorded.get("pages", {})
        self._searches: dict[str, list[dict]] = recorded.get("searches", {})

    def page(self, url: str) -> str | None:
        return self._pages.get(url.rstrip("/"))

    def search(self, query: str) -> list[dict]:
        return list(self._searches.get(query, []))


class BrightDataFetcher:
    """Bright Data's Web Unlocker for pages and its SERP API for searches. The key comes from the
    environment (BRIGHTDATA_API_KEY) and is sent in a header only; it is never logged."""

    URL = "https://api.brightdata.com/request"

    def __init__(self, timeout_s: float = 12.0) -> None:
        self._key = os.environ.get("BRIGHTDATA_API_KEY", "")
        self._unlocker = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker1")
        self._serp = os.environ.get("BRIGHTDATA_SERP_ZONE", "serp_api1")
        self._timeout = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _request(self, zone: str, url: str) -> str | None:
        body = json.dumps({"zone": zone, "url": url, "format": "raw"}).encode()
        req = urllib.request.Request(
            self.URL,
            data=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as res:  # noqa: S310 (fixed host)
            return res.read(2_000_000).decode("utf-8", "replace")

    def page(self, url: str) -> str | None:
        return self._request(self._unlocker, url) if self.configured else None

    def search(self, query: str) -> list[dict]:
        if not self.configured:
            return []
        q = urllib.parse.quote_plus(query)
        raw = self._request(self._serp, f"https://www.google.com/search?q={q}&brd_json=1")
        organic = (json.loads(raw or "{}") or {}).get("organic", [])
        return [
            {
                "url": hit.get("link", ""),
                "title": hit.get("title", ""),
                "snippet": hit.get("description", ""),
            }
            for hit in organic[:10]
        ]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _host(raw: str) -> str:
    host = raw.split("//")[-1].split("/")[0].lower().strip()
    return host[4:] if host.startswith("www.") else host


def check_building_site(inputs: WebInputs, fetcher: Fetcher) -> WebLine:
    if not inputs.website_host:
        return WebLine("building_site", "not_checked", "Not checked (no website on record).")
    html = fetcher.page(f"https://{inputs.website_host}")
    if not html:
        return WebLine(
            "building_site", "not_checked", "Not checked (the building's site did not open)."
        )
    text = _text(html)
    parts: list[str] = []
    ok = True
    if inputs.ad_beds is not None:
        listed = re.search(rf"\b{inputs.ad_beds}\s*(bed|br|bd|bedroom)s?\b", text, re.I) is not None
        parts.append(
            f"lists a {inputs.ad_beds} bed plan"
            if listed
            else f"lists no {inputs.ad_beds} bed plan"
        )
        ok = ok and listed
    if inputs.site_phone_hash:
        hashes = {phone_hash(found, inputs.salt) for found in _PHONE.findall(text)}
        same = inputs.site_phone_hash in hashes
        parts.append(f"its phone is the office number on record: {'yes' if same else 'no'}")
        ok = ok and same
    if not parts:
        return WebLine(
            "building_site", "not_checked", "Not checked (nothing on the site to compare)."
        )
    return WebLine(
        "building_site",
        "matches" if ok else "doesnt_match",
        f"The building's own site ({inputs.website_host}) {'; '.join(parts)}.",
    )


def check_ad_link(inputs: WebInputs, fetcher: Fetcher) -> WebLine:
    hosts = [_host(h) for h in inputs.ad_hosts if h]
    openable = [h for h in hosts if not NEVER_OPEN.search(h)]
    if not openable:
        why = "a Facebook link is never opened" if hosts else "the ad has no link"
        return WebLine("ad_link", "not_checked", f"Not checked ({why}).")
    record = _host(inputs.website_host) if inputs.website_host else None
    for host in openable:
        if record and host == record:
            return WebLine(
                "ad_link", "matches", f"The ad's link goes to the building's own site ({host})."
            )
        html = fetcher.page(f"https://{host}")
        name = (inputs.building_name or "").strip().lower()
        if html and name and name in _text(html).lower():
            return WebLine(
                "ad_link",
                "doesnt_match",
                f"The ad's link ({host}) is a different site that uses the building's name.",
            )
    return WebLine(
        "ad_link", "warning", f"The ad's link ({openable[0]}) is not the building's own site."
    )


def _first_sentence(text: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.strip().rstrip(".!?")
        if len(words.split()) >= 6 and not _MONEY.search(words) and not _PHONE.search(words):
            return words[:160]
    return None


def check_elsewhere(inputs: WebInputs, fetcher: Fetcher) -> WebLine:
    sentence = _first_sentence(inputs.ad_text)
    if not sentence:
        return WebLine(
            "elsewhere", "not_checked", "Not checked (the ad has no sentence to search)."
        )
    hits = [
        h for h in fetcher.search(f'"{sentence}"') if not NEVER_OPEN.search(_host(h.get("url", "")))
    ]
    if not hits:
        return WebLine("elsewhere", "matches", "No other listing online uses this ad's wording.")
    other_price = 0
    for hit in hits:
        prices = {int(m.replace(",", "")) for m in _MONEY.findall(hit.get("snippet", ""))}
        if inputs.ad_rent is not None and prices and inputs.ad_rent not in prices:
            other_price += 1
    noun = "listing" if len(hits) == 1 else "listings"
    text = f"Found this ad's wording in {len(hits)} other {noun} online"
    if other_price:
        text += f", {other_price} at a different price"
    return WebLine("elsewhere", "doesnt_match" if other_price else "warning", text + ".")


CHECKS: dict[Check, Callable[[WebInputs, Fetcher], WebLine]] = {
    "building_site": check_building_site,
    "ad_link": check_ad_link,
    "elsewhere": check_elsewhere,
}


def run_web_checks(
    inputs: WebInputs,
    fetcher: Fetcher,
    budget_s: float = BUDGET_S,
    on_line: Callable[[WebLine], None] | None = None,
) -> WebReport:
    """The three checks in parallel under one time limit. Never raises; never blocks past it."""
    import time

    start = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=len(CHECKS))
    futures = {pool.submit(fn, inputs, fetcher): name for name, fn in CHECKS.items()}
    done, _late = wait(futures, timeout=budget_s)
    lines: list[WebLine] = []
    for future, name in futures.items():
        if future in done:
            try:
                line = future.result()
            except Exception:
                line = WebLine(name, "not_checked", "Not checked (the web could not be read).")
        else:
            line = WebLine(name, "not_checked", "Not checked (time limit).")
        lines.append(line)
        if on_line is not None:
            on_line(line)
    pool.shutdown(wait=False, cancel_futures=True)  # a late fetch never holds the case
    return WebReport(lines=lines, seconds=round(time.monotonic() - start, 2))


class WebJob:
    """The web checks for one case, started when the case starts so the text answer is never
    held up. The web lines go to `on_line` (the trace) as they finish; `text()` waits for them, up
    to the time limit, and returns what the web sub-agent reads."""

    def __init__(
        self,
        inputs: WebInputs,
        fetcher: Fetcher,
        budget_s: float = BUDGET_S,
        on_line: Callable[[WebLine], None] | None = None,
    ) -> None:
        import threading

        self._inputs, self._fetcher, self._budget = inputs, fetcher, budget_s
        self._on_line = on_line
        self._report: WebReport | None = None
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            self._report = run_web_checks(self._inputs, self._fetcher, self._budget, self._on_line)
        finally:
            self._done.set()

    def start(self) -> WebJob:
        self._thread.start()
        return self

    def report(self) -> WebReport | None:
        self._done.wait(self._budget + 1.0)
        return self._report

    def text(self) -> str:
        report = self.report()
        return web_facts_text(report) if report else "The web checks did not finish in time."


def web_facts_text(report: WebReport | Iterable[WebLine]) -> str:
    """The web sub-agent's one reading tool returns this: one fact per line, with its source."""
    lines = report.lines if isinstance(report, WebReport) else list(report)
    return "\n".join(f"{line.check}: {line.status}: {line.text} (LIVE, web)" for line in lines)

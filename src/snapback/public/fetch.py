"""How the public lookups get their JSON: live over HTTPS, or from recorded answers.

A LIVE case calls the public service (Census, RDAP). A FIXTURE case, and every test, reads
`fixtures/public/recorded.json` instead, so nothing in CI touches the network. A fetch that
fails for any reason (timeout, HTTP error, bad JSON, no recording) is `None`, and the caller
reads that as "not checked", never as a finding.
"""

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx

from snapback.contracts import DataSource

log = logging.getLogger("snapback.public")
# httpx logs every request URL at INFO, and a SerpApi call carries its key in the query string.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)
RECORDED = Path(__file__).resolve().parents[3] / "fixtures" / "public" / "recorded.json"
USER_AGENT = "snapback-hackprinceton/1.0 (public-record checks; contact via repo)"


class Fetcher(Protocol):
    source: DataSource

    def get(self, kind: str, key: str, url: str, timeout: float) -> dict[str, Any] | None:
        """`kind` ("census", "rdap") and `key` (the question) name a recording; `url` is the
        live request. Returns the parsed JSON object or None."""
        ...


class LiveFetcher:
    source = DataSource.LIVE

    def get(self, kind: str, key: str, url: str, timeout: float) -> dict[str, Any] | None:
        try:
            response = httpx.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if response.status_code != 200:
                return None
            body = response.json()
            return body if isinstance(body, dict) else None
        except Exception as error:  # a lookup that broke is a lookup that did not happen
            log.warning("%s lookup failed (%s); not checked", kind, type(error).__name__)
            return None


class RecordedFetcher:
    """Answers from `fixtures/public/recorded.json`: {kind: {key: response}}. FIXTURE data."""

    source = DataSource.FIXTURE

    def __init__(self, path: Path = RECORDED) -> None:
        self._path = path

    def get(self, kind: str, key: str, url: str, timeout: float) -> dict[str, Any] | None:
        try:
            recorded = json.loads(self._path.read_text(encoding="utf-8"))
            found = recorded.get(kind, {}).get(key)
        except (OSError, ValueError):
            return None
        return found if isinstance(found, dict) else None


def fetcher_for(source: DataSource) -> Fetcher:
    return LiveFetcher() if source is DataSource.LIVE else RecordedFetcher()

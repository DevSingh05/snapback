"""Texas public records for a rental ad: the Comptroller, HUD's assisted-housing list, and the
City of Houston's address points. Information only: no verdict reads any of it.

Three lookups, each free and keyless, each one its own source line on the card:

  1. Texas Comptroller, Active Franchise Taxpayers (data.texas.gov `9cir-efmm`). If the ad names
     a management company: is it an active Texas company, and since when. "Not found" is an
     information line only, because sole proprietors are not on the list.
  2. HUD Multifamily Properties, Assisted (HUD's ArcGIS service, state TX). For a HUD-assisted
     building at the ad's street address: the manager company on HUD's record, and whether the
     ad's phone is one of the manager's numbers on that record. The mismatch is an information
     line: the CoStar phone rule compares a hash held on the property record (`site_phone_hash`),
     and feeding a second source into it is a rule change that needs approval.
  3. City of Houston Site Addresses (ArcGIS `COH_SiteAddresses`). An exact address point, as a
     fallback when the Census geocoder misses (pass `geocoder_hit=True` to skip it).

LIVE calls need `SNAPBACK_TX_RECORDS=1` and a LIVE run. Each call has a 3 s deadline, and any
error (timeout, bad status, odd body) means "not checked": no line, never a "not found". Nothing
is cached or logged: the URL carries the company and street. A phone number is compared in
memory and never kept. Only company names are shown, never a person's name.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

import httpx

from snapback.adapters.costar_residential import SUFFIXES, normalize_address
from snapback.contracts import DataSource, RecordLine

logging.getLogger("httpx").setLevel(logging.WARNING)

COMPTROLLER_URL = "https://data.texas.gov/resource/9cir-efmm.json"
HUD_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
    "MULTIFAMILY_PROPERTIES_ASSISTED/FeatureServer/0/query"
)
HOUSTON_URL = (
    "https://services.arcgis.com/NummVBqZSIJKUeVR/arcgis/rest/services/"
    "COH_SiteAddresses/FeatureServer/0/query"
)
TIMEOUT_S = 3.0
MAX_BODY_BYTES = 1024 * 1024
MAX_TEXT = 2_000

SRC_COMPTROLLER = "Texas Comptroller"
SRC_HUD = "HUD"
SRC_HOUSTON = "City of Houston"

Get = Callable[[str, Mapping[str, str]], Any]

_NOISE = frozenset(
    {"llc", "inc", "co", "corp", "corporation", "company", "ltd", "lp", "llp", "the"}
)
_DIRECTIONS = frozenset({"n", "s", "e", "w"})
_STREET_ENDS = frozenset(SUFFIXES.values()) - _DIRECTIONS | {"way", "trl", "loop", "fwy"}
_ACTIVE = "A"


def _http_get_json(url: str, params: Mapping[str, str]) -> Any:
    """One GET with a hard 3 s limit, a size cap and no redirects. Raises on anything odd."""
    body = b""
    with (
        httpx.Client(timeout=httpx.Timeout(TIMEOUT_S), follow_redirects=False) as client,
        client.stream("GET", url, params=dict(params)) as response,
    ):
        if response.status_code != 200:
            raise httpx.HTTPError("status")
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                raise httpx.HTTPError("too large")
    return json.loads(body)


# --- 1. Comptroller ---------------------------------------------------------------------


def _core_words(name: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return [w for w in words if w not in _NOISE]


def comptroller_line(company: str | None, get: Get) -> RecordLine | None:
    """Active, listed-but-not-active, or not listed. None when there is no company to look up
    or the call failed (not checked)."""
    from snapback.agent.rules.contact import same_company

    said = " ".join((company or "").split())[:120]
    words = _core_words(said)[:2]
    if not words:
        return None
    where = f"upper(taxpayer_name) like '{' '.join(words).upper()}%'"
    try:
        rows = get(COMPTROLLER_URL, {"$where": where, "$limit": "25"})
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    mine = [
        row
        for row in rows
        if isinstance(row, dict) and same_company(said, str(row.get("taxpayer_name") or ""))
    ]
    active = [r for r in mine if str(r.get("right_to_transact_business_code")) == _ACTIVE]
    if active:
        years = [
            _year(r.get("sos_charter_date") or r.get("responsibility_beginning_date"))
            for r in active
        ]
        known = [y for y in years if y is not None]
        return _line(
            "comptroller_active", SRC_COMPTROLLER, company=said, year=min(known, default=None)
        )
    if mine:
        return _line("comptroller_inactive", SRC_COMPTROLLER, company=said)
    return _line("comptroller_none", SRC_COMPTROLLER, company=said)


def _year(value: object) -> int | None:
    match = re.match(r"(\d{4})-", str(value or ""))
    return int(match.group(1)) if match else None


# --- the street in the ad ---------------------------------------------------------------


def street_of(text: str) -> str | None:
    """The first "number street-name suffix" in the ad, normalised ("100 fixture ln"), or None."""
    words = normalize_address(text[:MAX_TEXT]).split()
    for i, word in enumerate(words):
        if not (word.isdigit() and len(word) <= 6):
            continue
        for n in range(1, 5):
            tail = words[i + 1 : i + 1 + n + 1]
            if len(tail) < n + 1:
                break
            name, end = tail[:n], tail[n]
            if (
                end in _STREET_ENDS
                and not any(w.isdigit() for w in name)
                and not set(name) & {"unit"}
            ):
                return " ".join([word, *name, end])
    return None


def _without_direction(street: str) -> str:
    return " ".join(w for w in street.split() if w not in _DIRECTIONS)


# --- 2. HUD -----------------------------------------------------------------------------


def _digits(phone: object) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits


def hud_lines(text: str, ad_phones: list[str], get: Get) -> list[RecordLine]:
    """The manager on HUD's record for the ad's street address, and a line if the ad's phone is
    not one of the manager's numbers there. Empty when the street is not a HUD-assisted building
    or the call failed."""
    street = street_of(text)
    if street is None:
        return []
    number, *name, _end = street.split()
    name = [w for w in name if w not in _DIRECTIONS]
    if not name:
        return []
    where = f"STD_ST='TX' AND UPPER(STD_ADDR) LIKE '{number} %{name[0].upper()}%'"
    params = {
        "where": where,
        "outFields": "STD_ADDR,STD_ZIP5,MGMT_AGENT_ORG_NAME,"
        "MGMT_CONTACT_MAIN_PHN_NBR,PROPERTY_ON_SITE_PHONE_NUMBER",
        "returnGeometry": "false",
        "resultRecordCount": "10",
        "f": "json",
    }
    try:
        body = get(HUD_URL, params)
    except Exception:
        return []
    features = body.get("features") if isinstance(body, dict) else None
    if not isinstance(features, list):
        return []
    want = _without_direction(street)
    rows = []
    for feature in features:
        attrs = feature.get("attributes") if isinstance(feature, dict) else None
        if (
            isinstance(attrs, dict)
            and _without_direction(normalize_address(str(attrs.get("STD_ADDR") or ""))) == want
        ):
            rows.append(attrs)
    if len(rows) != 1:  # none, or two buildings on one street number: never pick one
        return []
    row = rows[0]
    manager = " ".join(str(row.get("MGMT_AGENT_ORG_NAME") or "").split())[:80]
    if not manager:
        return []
    lines = [_line("hud_manager", SRC_HUD, company=manager)]
    theirs = {
        _digits(row.get("MGMT_CONTACT_MAIN_PHN_NBR")),
        _digits(row.get("PROPERTY_ON_SITE_PHONE_NUMBER")),
    } - {""}
    ours = {_digits(p) for p in ad_phones[:5]} - {""}
    if theirs and ours and not ours & theirs:
        lines.append(_line("hud_phone_differs", SRC_HUD, company=manager))
    return lines


# --- 3. City of Houston -----------------------------------------------------------------


def address_point_line(text: str, get: Get) -> RecordLine | None:
    street = street_of(text)
    if street is None:
        return None
    params = {
        "where": f"fulladdr='{street.upper()}'",
        "outFields": "fulladdr,zipcode,source",
        "returnGeometry": "false",
        "resultRecordCount": "2",
        "f": "json",
    }
    try:
        body = get(HOUSTON_URL, params)
    except Exception:
        return None
    features = body.get("features") if isinstance(body, dict) else None
    if not isinstance(features, list) or not features:
        return None
    attrs = features[0].get("attributes") if isinstance(features[0], dict) else None
    if not isinstance(attrs, dict):
        return None
    zip_code = str(attrs.get("zipcode") or "")
    return _line(
        "address_point",
        SRC_HOUSTON,
        zip_code=zip_code if re.fullmatch(r"\d{5}", zip_code) else None,
    )


# --- all together -----------------------------------------------------------------------


def _line(key: str, source: str, **facts: Any) -> RecordLine:
    # data_source is stamped by `lookup`; the placeholder never leaves this module
    return RecordLine(key=key, source=source, data_source=DataSource.LIVE, **facts)


def lookup(
    text: str,
    data_source: DataSource,
    *,
    get: Get | None = None,
    geocoder_hit: bool | None = None,
) -> list[RecordLine]:
    """Every line the three registries give for this ad, each stamped with `data_source`.

    The lookups run side by side under one 3 s wait; one that fails or runs late leaves its
    lines out. `geocoder_hit=True` (the Census geocoder found the address) skips the Houston
    address-point fallback."""
    from snapback.agent.intake.fields import extract_contacts

    fetch = get or _http_get_json
    claims = extract_contacts(text[:MAX_TEXT])
    jobs: list[Callable[[], list[RecordLine]]] = [
        lambda: _as_list(comptroller_line(claims.company, fetch)),
        lambda: hud_lines(text, list(claims.phones), fetch),
    ]
    if geocoder_hit is not True:
        jobs.append(lambda: _as_list(address_point_line(text, fetch)))
    pool = ThreadPoolExecutor(max_workers=len(jobs))
    try:
        futures = [pool.submit(job) for job in jobs]
        wait(futures, timeout=TIMEOUT_S + 0.5)
        lines: list[RecordLine] = []
        for future in futures:
            if future.done() and future.exception() is None:
                lines.extend(future.result())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return [line.model_copy(update={"data_source": data_source}) for line in lines]


def _as_list(line: RecordLine | None) -> list[RecordLine]:
    return [line] if line is not None else []


def public_records(
    text: str, data_source: DataSource, *, geocoder_hit: bool | None = None
) -> list[RecordLine]:
    """The entry point lane A's lookups call: nothing unless SNAPBACK_TX_RECORDS is on and the
    run is LIVE. A fixture run, and so every test, never calls out."""
    from snapback.settings import get_settings

    if data_source is not DataSource.LIVE or not get_settings().snapback_tx_records:
        return []
    try:
        return lookup(text, data_source, geocoder_hit=geocoder_hit)
    except Exception as error:
        logging.getLogger(__name__).warning(
            "tx records lookup failed (%s); treated as not looked up", type(error).__name__
        )
        return []

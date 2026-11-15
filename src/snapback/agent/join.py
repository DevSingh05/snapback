"""A10 (issue #97): join lane D's adapters to the agent.

A check runs on the building's own record: the CoStar record (D1) and the for-sale lookup
(D7) feed lane A's price, unit and contact rules.

The twin (locate) and the challenge are still stand-ins until lanes V and D land them (V2,
D3), and a stand-in is fixture data. So they are used in a fixture case only. A live case, or
any case on a live record, has no twin and no challenge: nothing from a fixture is ever put
beside a real record.

Nothing here logs or returns a value from a record. The rules turn it into statuses.
"""

import logging
import re
import threading
from pathlib import Path
from typing import Protocol

from snapback.adapters.vexcel import known_capture
from snapback.agent.intake import Listing
from snapback.agent.intake.claims import extract_claims
from snapback.agent.locate_live import LiveLocate, LiveOutcome
from snapback.agent.modules import ChallengeOutcome, FixtureModules
from snapback.agent.rules import apply_rules, check_price
from snapback.agent.rules.ad_vs_record import compare_ad_to_record
from snapback.agent.rules.contact import check_authority
from snapback.agent.rules.owner import check_owner
from snapback.agent.scope import ListingScope
from snapback.contracts import (
    AdNote,
    AuthorityResult,
    DataSource,
    DomainCheck,
    FloorPlanCandidate,
    ForSaleMatch,
    ForSaleStatus,
    LicenseResult,
    LocateResult,
    LocateStatus,
    OwnerResult,
    PhotoLocation,
    PlaceCheck,
    PriceResult,
    PriceStatus,
    PropertyRecord,
    PublicStatus,
    RecordLine,
    RentalHouse,
    RuleHit,
    SpotCandidate,
    SpotRanking,
)

log = logging.getLogger("snapback.join")


class KitMissing(Exception):
    """The record was asked for and the kit is not on this machine."""

    def __init__(self) -> None:
        super().__init__(
            "The CoStar kit is not on this server, so there is no record to read. "
            "See the README, 'Get the CoStar kit', or run with SNAPBACK_DATA_SOURCE=fixture."
        )


class Lookups(Protocol):
    """What the join needs from lane D."""

    def record(self, property_id: str) -> PropertyRecord | None:
        """The record for our id, or None if we hold none."""
        ...

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        """Is the home in the listing for sale or just rented? None means not looked up."""
        ...

    def license(self, listing_text: str) -> LicenseResult | None:
        """Does a poster who claims a real estate licence hold one? None means not looked up."""
        ...

    def owner(self, listing_text: str) -> OwnerResult | None:
        """Who owns the home in the listing, by the county roll? None means no owner data."""
        ...

    # Optional, so lookups written before A24 still fit: `license_number(number, listing_text)`
    # looks up a license number the renter typed, by the same rules as `license`.


def license_of(lookups: Lookups, listing_text: str) -> LicenseResult | None:
    """Lane D's licence answer for this listing, or None when nothing was looked up.

    A lookup that broke is a lookup that did not happen: it must not stop the check, and it
    must not read as "looked up, nothing found". Lookups written before D10 have no licence
    method, and that is "not looked up" too. No value is logged.
    """
    lookup = getattr(lookups, "license", None)
    if lookup is None or not listing_text:
        return None
    try:
        return lookup(listing_text)
    except Exception as error:
        log.warning("licence lookup failed (%s); treated as not looked up", type(error).__name__)
        return None


def owner_of(lookups: Lookups, listing_text: str) -> OwnerResult | None:
    """Lane D's owner of record for the home in this listing (D12), or None when there is none."""
    lookup = getattr(lookups, "owner", None)
    if lookup is None or not listing_text:
        return None
    try:
        return lookup(listing_text)
    except Exception as error:
        log.warning("owner lookup failed (%s); treated as not looked up", type(error).__name__)
        return None


def owner_of_county(
    lookups: object, listing_text: str, place: PlaceCheck | None
) -> OwnerResult | None:
    """The owner of record, asked only about a Harris County address (HCAD's roll is keyed by
    street alone, so another county's street must never be matched against a Harris one)."""
    from snapback.public.census import in_harris_county

    if not in_harris_county(listing_text, place):
        return None
    return owner_of(lookups, listing_text)  # type: ignore[arg-type]


def public_checks_of(
    lookups: object, listing_text: str
) -> tuple[PlaceCheck | None, DomainCheck | None]:
    """The Census address check and the RDAP link-domain age for this listing, run side by side
    under the public-data time limit. Either is None when not looked up (no address or link in
    the ad, a flag off, or a lookup that broke): a lookup that broke is a lookup that did not
    happen. No address, domain or name is logged."""
    place_fn = getattr(lookups, "place_check", None)
    domain_fn = getattr(lookups, "domain_check", None)
    if not listing_text or (place_fn is None and domain_fn is None):
        return None, None
    from concurrent.futures import ThreadPoolExecutor

    def safe(fn: object) -> object:
        if fn is None:
            return None
        try:
            return fn(listing_text)  # type: ignore[operator]
        except Exception as error:
            log.warning("public lookup failed (%s); treated as not looked up", type(error).__name__)
            return None

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="public-check") as pool:
        place, domain = pool.submit(safe, place_fn), pool.submit(safe, domain_fn)
        return place.result(), domain.result()  # type: ignore[return-value]


MAX_OFFICE_CHARS = 80
# A "company" that is really a street address (11 kit buildings with scans): never shown.
_STREET_WORDS = (
    r"st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court|pkwy|parkway|"
    r"hwy|highway|fwy|freeway|pl|place|cir|circle|trl|trail|sq|square|ter|terrace|loop"
)
ADDRESS_LIKE = re.compile(
    rf"\b\d{{1,6}}\s+(?:[A-Za-z0-9.'-]+\s+){{0,4}}(?:{_STREET_WORDS})\b", re.I
)
# A name that opens with a bare number ("4821 Quillfeather LLC") is an address with a suffix.
_STARTS_WITH_NUMBER = re.compile(r"^\d{1,6}\s")


def _first_two_words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.lower())[:2])


def _looks_like_address(company: str, street_address: str | None) -> bool:
    if ADDRESS_LIKE.search(company) or _STARTS_WITH_NUMBER.match(company):
        return True
    words = _first_two_words(company)
    return len(words) == 2 and words == _first_two_words(street_address or "")


def matched_office_of(lookups: object, locate: LocateResult | None) -> str | None:
    """The office on CoStar's record for the home a photo was placed in (the first such photo),
    company name only. None when no photo was placed elsewhere, the home is not held, or its
    record names no company. Nothing is looked up for the claimed home."""
    if lookups is None or locate is None:
        return None
    for photo in locate.photos:
        found = photo.matched_property_id
        if photo.status is not LocateStatus.LOCATED_ELSEWHERE or not found:
            continue
        record = lookups.record(found)  # type: ignore[attr-defined]
        company = (record.manager_company or "").strip() if record is not None else ""
        if not company or _looks_like_address(company, record.street_address):
            return None
        return company[:MAX_OFFICE_CHARS]
    return None


class KitLookups:
    """Lane D's adapters. The kit is parsed once and kept for the life of the process."""

    def __init__(self, source: DataSource, kit_dir: Path | None = None) -> None:
        self.source = source
        self._kit_dir = kit_dir
        self._records: dict[str, PropertyRecord] | None = None
        self._rentals: list[RentalHouse] | None = None
        self._lock = threading.Lock()

    def records(self) -> dict[str, PropertyRecord]:
        """Every record in the kit by our id, parsed once. For routes that need more than one."""
        from snapback.adapters import costar_jsonl

        with self._lock:
            if self._records is None:
                try:
                    records = costar_jsonl.load_records(self.source, self._kit_dir)
                except costar_jsonl.KitNotFoundError:
                    raise KitMissing from None
                # Houses (residential listings with a Matterport model) join the buildings,
                # so a house photo can be identified and a house id can be claimed.
                try:
                    from snapback.adapters import costar_residential

                    houses = costar_residential.house_records(self.source, self._kit_dir)
                except Exception as error:  # a broken residential file must not hide buildings
                    log.warning("house records not read (%s)", type(error).__name__)
                    houses = {}
                for property_id, house in houses.items():
                    records.setdefault(property_id, house)
                self._records = records
            return self._records

    def record(self, property_id: str) -> PropertyRecord | None:
        return self.records().get(property_id)

    def rentals(self) -> list[RentalHouse]:
        """The active house rentals in the kit (search supply), read once and kept."""
        with self._lock:
            if self._rentals is None:
                try:
                    from snapback.adapters import costar_residential

                    self._rentals = costar_residential.rental_houses(self.source, self._kit_dir)
                except Exception as error:  # a broken residential file must not hide buildings
                    log.warning("house rentals not read (%s)", type(error).__name__)
                    self._rentals = []
            return self._rentals

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        try:
            from snapback.adapters import costar_residential
        except ImportError:
            return None  # lane D's lookup (D7) is not here: nothing was looked up
        try:
            return costar_residential.for_sale_lookup(listing_text, self.source, self._kit_dir)
        except Exception as error:
            # A lookup that broke is a lookup that did not happen. It must not stop the
            # check, and it must not read as "looked up, nothing found". No value is logged.
            log.warning(
                "for-sale lookup failed (%s); treated as not looked up", type(error).__name__
            )
            return None

    def license(self, listing_text: str) -> LicenseResult | None:
        # The licence list is a public service outside this machine (D10, #128). A fixture
        # run, and so every test, never calls out: only a live run looks anyone up.
        if self.source is not DataSource.LIVE:
            return None
        try:
            from snapback.adapters import trec
        except ImportError:
            return None  # lane D's lookup (D10) is not here: nothing was looked up
        return trec.check_license(listing_text)

    def license_number(self, number: str, listing_text: str) -> LicenseResult | None:
        """D10 for a number the renter typed (A24 stretch): a live run only, like `license`."""
        if self.source is not DataSource.LIVE:
            return None
        try:
            from snapback.adapters import trec
        except ImportError:
            return None
        return trec.check_license_number(number, listing_text)

    def owner(self, listing_text: str) -> OwnerResult | None:
        # D12 (#130): the county owner roll (HCAD), filtered to the kit's Houston houses and kept
        # under data/hcad/. No lookup file, or no street match, is None: ownership not checked.
        # Lane A fills poster_says_owner and published_rule; a person's name never comes back.
        # A company is named only when we know it: a row in the published-rule table, or an
        # office on record in the kit for this home (ruling, round 5 on #160).
        # The company the poster names is compared with the roll inside the adapter (round 6).
        from snapback.adapters.hcad import lookup_owner
        from snapback.agent.intake.fields import extract_contacts

        match = self.for_sale(listing_text)
        offices = getattr(match, "offices", None) or ()
        return lookup_owner(listing_text, offices, extract_contacts(listing_text).company)

    def public_records(
        self, listing_text: str, geocoder_hit: bool | None = None
    ) -> list[RecordLine]:
        """Texas public records (Comptroller, HUD manager, Houston address point): a LIVE run
        with SNAPBACK_TX_RECORDS on only. Information lines; nothing here reaches `decide`."""
        from snapback.adapters import tx_records

        return tx_records.public_records(listing_text, self.source, geocoder_hit=geocoder_hit)

    def place_check(self, listing_text: str) -> PlaceCheck | None:
        """Census Geocoder on the address in the ad. A LIVE run calls it; a fixture run reads a
        recorded answer and, with none recorded, looked nothing up."""
        from snapback.public import census, fetch
        from snapback.settings import get_settings

        settings = get_settings()
        address = census.address_in(listing_text) if settings.snapback_census_geocoder else None
        if address is None:
            return None
        found = census.check(
            address, fetch.fetcher_for(self.source), settings.snapback_public_timeout_s
        )
        if found.status is PublicStatus.NOT_CHECKED and self.source is not DataSource.LIVE:
            return None
        return found

    def domain_check(self, listing_text: str) -> DomainCheck | None:
        """RDAP age of the first non-platform link's domain. Same LIVE and fixture rules."""
        from datetime import UTC, datetime

        from snapback.public import fetch, rdap
        from snapback.settings import get_settings

        settings = get_settings()
        host = rdap.link_host(listing_text) if settings.snapback_rdap else None
        if host is None:
            return None
        found = rdap.check(
            host,
            fetch.fetcher_for(self.source),
            today=datetime.now(UTC).date(),
            timeout=settings.snapback_public_timeout_s,
        )
        if found.status is PublicStatus.NOT_CHECKED and self.source is not DataSource.LIVE:
            return None
        return found

    def lens_for_sale(self, listing_text: str) -> ForSaleMatch | None:
        """Reverse image search of the ad's own photo links (Google Lens via SerpApi). LIVE only,
        needs SERPAPI_API_KEY; the caller asks only when CoStar has no scan or for-sale record."""
        if self.source is not DataSource.LIVE:
            return None
        from snapback.public import fetch, lens
        from snapback.settings import get_settings

        settings = get_settings()
        if not settings.snapback_lens or settings.serpapi_api_key is None:
            return None
        return lens.check(
            listing_text,
            fetch.fetcher_for(self.source),
            settings.serpapi_api_key.get_secret_value(),
            settings.snapback_lens_timeout_s,
        )

    def for_sale_at(self, listing_text: str, lat: float, lon: float) -> ForSaleMatch | None:
        """The same lookup, also matching any home within 40 m of this point."""
        try:
            from snapback.adapters import costar_residential

            return costar_residential.for_sale_lookup(
                listing_text, self.source, self._kit_dir, lat=lat, lon=lon
            )
        except Exception as error:
            log.warning(
                "for-sale lookup by position failed (%s); treated as not looked up",
                type(error).__name__,
            )
            return None


class NoStandIn(RuntimeError):
    """Something asked for the twin or the challenge in a case that has no stand-in for them."""


class JoinedModules:
    """What the agent calls: the record parts from lane D, the rest from the stand-in.

    `stand_in` is None for a live case. Stand-ins are fixture data, so a live case has no
    twin and no challenge until lanes V and D land the real ones: its photos read "not
    checked", nobody is asked to prove presence, and it cannot come out VERIFIED.
    """

    def __init__(
        self,
        *,
        stand_in: FixtureModules | None,
        listing: Listing,
        record: PropertyRecord | None,
        for_sale: ForSaleMatch | None,
        salt: str,
        record_source: DataSource | None,
        license: LicenseResult | None = None,
        owner: OwnerResult | None = None,
        place_check: PlaceCheck | None = None,
        domain_check: DomainCheck | None = None,
        live_locate: LiveLocate | None = None,
        photo_bytes: list[bytes] | None = None,
        lookups: Lookups | None = None,
        case_id: str = "",
    ) -> None:
        self._stand_in = stand_in
        self._listing = listing
        self._record = record
        self._for_sale = for_sale
        self._license = license
        self._owner = owner
        self._place_check = place_check
        self._domain_check = domain_check
        self._salt = salt
        self._record_source = record_source
        # A22: a live case places the renter's photos in the indexed twins (never a stand-in).
        self._live_locate = live_locate if stand_in is None else None
        self._photo_bytes = photo_bytes or []
        self._lookups = lookups
        self._case_id = case_id
        self._twin: bool | None = None
        self._outcome: LiveOutcome | None = None
        self._located = False
        self._adopt_lock = threading.Lock()

    # --- from the listing and the record ---------------------------------------------------

    def listing_scope(self, case_id: str) -> ListingScope:
        return self._listing.scope

    def rules(self, case_id: str) -> list[RuleHit]:
        # Intake read the text before the record was known. With the record's own website, a
        # credit-check link that goes to the building's own site is read again as the landlord's.
        self._identify(case_id)
        host = self._record.website_host if self._record is not None else None
        hits = (
            apply_rules(self._listing.text, own_host=host)
            if host
            else list(self._listing.rule_hits)
        )
        return [*hits, *self._new_domain_hits()]

    def _new_domain_hits(self) -> list[RuleHit]:
        """`link.new_domain` (RDAP): a link in the ad on a domain registered a few days ago."""
        from snapback.public import rdap
        from snapback.settings import get_settings

        if self._domain_check is None:
            return []
        hit = rdap.rule_hit(self._domain_check, get_settings().snapback_new_domain_days)
        return [hit] if hit is not None else []

    def place_check(self, case_id: str) -> PlaceCheck | None:
        return self._place_check

    def domain_check(self, case_id: str) -> DomainCheck | None:
        return self._domain_check

    def price(self, case_id: str) -> PriceResult | None:
        self._identify(case_id)
        listing = self._listing
        found = check_price(listing.listed_rent, self._record, beds=listing.beds, unit=listing.unit)
        if found.status is not PriceStatus.NOT_CHECKED or found.per_bed:
            return found
        # CoStar has no rent for this home (a house or condo it does not cover): HUD's typical
        # rent for the ZIP and size is the baseline, and the card names it.
        return self._hud_price(found)

    def _hud_price(self, found: PriceResult) -> PriceResult:
        from snapback.public import hud
        from snapback.settings import get_settings

        if not get_settings().snapback_hud_baseline:
            return found
        listing = self._listing
        zip_code = hud.zip_in(listing.text)
        if zip_code is None and self._place_check is not None:
            zip_code = self._place_check.zip  # the Census Geocoder found it from the address
        compared = hud.check_price(listing.listed_rent, listing.beds, zip_code)
        return found if compared is None else compared.model_copy(update={"unit": found.unit})

    def authority(self, case_id: str) -> AuthorityResult | None:
        # The listing brokerage on record may market the home as the manager may (ruling,
        # Sat 01:20). Lane D's lookup carries those names once D7 (#95) is on main.
        self._identify(case_id)
        offices = getattr(self._for_sale, "offices", None) or ()
        return check_authority(self._listing.contacts, self._record, self._salt, offices)

    def for_sale(self, case_id: str) -> ForSaleMatch | None:
        self._identify(case_id)
        return self._for_sale

    def license(self, case_id: str) -> LicenseResult | None:
        return self._license

    def matched_office(self, case_id: str, locate: LocateResult | None) -> str | None:
        """X1: the office on record for the home the photos were placed in, if elsewhere."""
        try:
            return matched_office_of(self._lookups, locate)
        except Exception as error:  # a lookup that breaks leaves the line out, never the case
            log.warning("matched office not read (%s)", type(error).__name__)
            return None

    def public_records(self, case_id: str) -> list[RecordLine]:
        """Texas public records for the ad's company and street. Not looked up is empty."""
        lookup = getattr(self._lookups, "public_records", None)
        if lookup is None or not self._listing.text:
            return []
        # The Census check already found the address: the Houston address-point fallback runs
        # only when Census missed, failed or was not asked.
        hit = self._place_check is not None and self._place_check.status is PublicStatus.FOUND
        try:
            found = (
                lookup(self._listing.text, geocoder_hit=True) if hit else lookup(self._listing.text)
            )
            return list(found or [])
        except Exception as error:  # a lookup that breaks leaves the lines out, never the case
            log.warning("public records not read (%s)", type(error).__name__)
            return []

    def ad_notes(self, case_id: str) -> list[AdNote]:
        """Ad vs record: the ad's claims against the home's record. No record, no notes."""
        self._identify(case_id)
        record = self._record
        aerial_on = None
        if record is not None:
            try:  # the date of a tile already held; never a network call
                aerial_on = known_capture(record, self._record_source or DataSource.LIVE)
            except Exception as error:
                log.warning("aerial date not read (%s)", type(error).__name__)
        return compare_ad_to_record(extract_claims(self._listing.text), record, aerial_on=aerial_on)

    def license_by_number(self, case_id: str, number: str) -> LicenseResult | None:
        """D10 again, with the number the renter gave (A24 stretch): the number goes straight to
        the lookup, with the ad's words for the name the poster claims, so the ad's length
        cannot hide it. None when nothing was looked up (no lookup, or it broke). The number is
        kept nowhere; the result holds only whether the state found it."""
        lookup = getattr(self._lookups, "license_number", None)
        if lookup is None:
            return None
        try:
            found = lookup(number, self._listing.text)
        except Exception as error:
            log.warning(
                "licence lookup failed (%s); treated as not looked up", type(error).__name__
            )
            return None
        if found is None:
            return None
        return found.model_copy(update={"number_from": "renter"})

    def owner(self, case_id: str) -> OwnerResult | None:
        # Lane D says who owns the home. What the poster says about owning it is added here.
        return check_owner(self._listing.contacts, self._owner)

    @property
    def record(self) -> PropertyRecord | None:
        """The property record this case runs on, if it has one (read-only)."""
        return self._record

    def record_source(self, case_id: str) -> DataSource | None:
        """Where the record parts came from, or None if there are none."""
        self._identify(case_id)
        if self._record is None and self._for_sale is None:
            return None
        return self._record_source

    def property_type(self, case_id: str) -> str | None:
        """The record's kind of home, once the home is known. None with no record."""
        self._identify(case_id)
        return self._record.property_type if self._record is not None else None

    # --- the twin and the challenge: stand-ins, and only in a fixture case -----------------

    def _live_twin(self) -> bool:
        """A live case has a twin when its claimed home is indexed, or when no home is claimed
        and the index is not empty. Decided once."""
        if self._twin is None:
            live, record = self._live_locate, self._record
            if live is None or not self._photo_bytes:
                self._twin = False
            elif record is None:
                self._twin = live.available(None, [])
            else:
                self._twin = bool(record.model_ids) and live.available(
                    record.property_id, record.model_ids
                )
        return self._twin

    def _live_outcome(self, case_id: str) -> LiveOutcome | None:
        with self._adopt_lock:
            if not self._located:
                self._located = True
                if self._live_twin() and self._live_locate is not None:
                    claimed = self._record.property_id if self._record else None
                    self._outcome = self._live_locate.locate(
                        case_id or self._case_id, self._photo_bytes, claimed
                    )
                    self._adopt_identified()
            return self._outcome

    def _identify(self, case_id: str) -> None:
        """With no claimed home, place the photos first: the home they identify gives the
        record that price, authority and for-sale are read from."""
        if self._record is None and self._live_locate is not None:
            self._live_outcome(case_id)

    def _adopt_identified(self) -> None:
        outcome = self._outcome
        if outcome is None or self._record is not None:
            return
        found = outcome.identified_property_id
        if found is None and getattr(outcome.result, "identified_by_scan", False):
            found = outcome.result.claimed_property_id
        if not found or self._lookups is None:
            return
        record = self._lookups.record(found)
        if record is None:
            return
        self._record = record
        self._record_source = record.source
        at = getattr(self._lookups, "for_sale_at", None)
        if at is not None and record.lat is not None and record.lon is not None:
            nearby = at(self._listing.text, record.lat, record.lon)
            held = self._for_sale
            downgrade = (
                held is not None
                and held.status is not ForSaleStatus.NONE
                and nearby is not None
                and nearby.status is ForSaleStatus.NONE
            )
            if nearby is not None and not downgrade:
                self._for_sale = nearby

    def has_twin(self, case_id: str) -> bool:
        if self._stand_in is None:
            return self._live_twin()
        # A building whose record has no 3D model has no twin, whatever the stand-in holds.
        if self._record is not None and not self._record.model_ids:
            return False
        return self._stand_in.has_twin(case_id)

    def photo_count(self, case_id: str) -> int:
        if not self.has_twin(case_id):
            return self._listing.photos  # the photos the renter actually sent
        if self._stand_in is None:
            return len(self._photo_bytes)
        return self._stand_in.photo_count(case_id)

    def floor_plans(self, case_id: str) -> list[FloorPlanCandidate]:
        if not self.has_twin(case_id) or self._stand_in is None:
            return []  # a live case has no floor-plan stand-in
        return self._stand_in.floor_plans(case_id)

    def live_points(self, case_id: str) -> dict:
        """The live run's matched pairs per photo id, for the evidence file only (E2b). Empty
        for a fixture case or when no live run placed anything."""
        if self._stand_in is not None or not self.has_twin(case_id):
            return {}
        outcome = self._live_outcome(case_id)
        return dict(outcome.points) if outcome is not None else {}

    def locate(self, case_id: str) -> LocateResult | None:
        if self.has_twin(case_id):
            if self._stand_in is None:
                outcome = self._live_outcome(case_id)
                if outcome is not None:
                    return outcome.result
            else:
                return self._stand_in.locate(case_id)
        # No twin to place photos in. Each photo sent is recorded as not checked, so the
        # card says there is no 3D scan to check against, not that no photos were sent.
        sent = self._listing.photos
        if not sent:
            return None
        # Naming the building's model says its scan exists and is not in our index, which
        # the card puts differently from "there is no scan". The id itself is never shown.
        models = self._record.model_ids if self._record else []
        return LocateResult(
            case_id=case_id,
            photos=[
                PhotoLocation(
                    photo_id=f"l{number}",
                    status=LocateStatus.NOT_INDEXED,
                    model_id=models[0] if models else None,
                )
                for number in range(1, sent + 1)
            ],
            claimed_property_id=self._record.property_id if self._record else None,
            thresholds_version="none",
        )

    def spot_ranking(self, case_id: str, model_id: str | None) -> SpotRanking | None:
        if self._stand_in is None or not self.has_twin(case_id):
            return None  # a live case has no spot ranking yet: it ends after locate
        return self._stand_in.spot_ranking(case_id, model_id)

    def new_code(self, case_id: str) -> str:
        return self._need_stand_in().new_code(case_id)

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        return self._need_stand_in().challenge(case_id, spot, code, text, attempt)

    @property
    def sent_messages(self) -> list[str]:
        return self._stand_in.sent_messages if self._stand_in is not None else []

    def _need_stand_in(self) -> FixtureModules:
        if self._stand_in is None:
            raise NoStandIn("a live case has no stand-in challenge")
        return self._stand_in

"""Shared data contracts between lanes.

Every lane reads and writes these shapes, so a change here can break three other lanes.
Change this file only through a pull request reviewed by the integrator lane.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataSource(StrEnum):
    """Where a case's data came from. Every screen and every number shows this label."""

    LIVE = "live"
    FIXTURE = "fixture"


class LocateStatus(StrEnum):
    """Result of placing one listing photo in the 3D twins we have indexed."""

    LOCATED_IN_CLAIMED = "located_in_claimed"  # geometrically verified inside the claimed property
    LOCATED_ELSEWHERE = "located_elsewhere"  # verified inside a different indexed property
    NOT_LOCATED = (
        "not_located"  # claimed home indexed, photo matches nowhere; or no claim and no single home
    )
    NOT_INDEXED = "not_indexed"  # the claimed property has no twin in our index


class PhotoLocation(BaseModel):
    """One listing photo and where (if anywhere) it was found."""

    photo_id: str
    status: LocateStatus
    model_id: str | None = None
    pano_id: str | None = None
    inliers: int | None = None
    inlier_ratio: float | None = None
    # Which twin the photo was placed in (claimed or not), for located_in_claimed and
    # located_elsewhere; for located_elsewhere these name the OTHER building (V2, #41).
    matched_model_id: str | None = None
    matched_property_id: str | None = None
    room_label: str | None = None  # Matterport's room classification, e.g. "Kitchen"
    # E0 (plan/ml-agent-plan.md 3b): what the verification measured, kept so the evidence file
    # can show it. All optional: None means "not recorded", never "zero".
    spread: float | None = None  # how widely the matched points cover the photo (0 to 1)
    rival_ratio: float | None = None  # best rival building's inliers over this one's
    bar_failed: Literal["inliers", "ratio", "spread", "ambiguity"] | None = None


class AuthorityStatus(StrEnum):
    """Does the poster match the contact on the property record?"""

    MATCHES_RECORD = "matches_record"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class PresenceStatus(StrEnum):
    """State of the proof-of-presence challenge. Presence is never the same thing as authority."""

    NOT_REQUESTED = "not_requested"
    WAITING = "waiting"  # includes "no reply yet": an honest landlord gets time
    PROVEN = "proven"
    FORGED = "forged"  # the reply was a reused listing photo, a tour screenshot, or similar


class Evidence(BaseModel):
    """Everything the verdict is allowed to look at for one case."""

    case_id: str
    source: DataSource
    photos: list[PhotoLocation] = Field(default_factory=list)
    authority: AuthorityStatus = AuthorityStatus.UNKNOWN
    presence: PresenceStatus = PresenceStatus.NOT_REQUESTED
    forgery_reason: str | None = None
    price_flag: bool = False  # listed rent is far below comparable units
    payment_flag: bool = False  # asked for a deposit before viewing, or an irreversible payment
    rule_flag: bool = False  # any red-flag rule fired, including pressure and links
    # A7 (#67). Each of these holds a case at HOLD; none of them is proof, so none gives DONT_PAY.
    for_sale_flag: bool = False  # the home is listed for sale, not for rent
    recently_rented_flag: bool = False  # the record shows it was rented out recently
    phone_flag: bool = False  # the phone in the listing is not the leasing office on record
    # A23 (H1): the phone in the listing IS the leasing office's on record. VERIFIED needs it.
    phone_confirmed: bool = False
    # the phone is not the office's, but an active licence by number is sponsored by the
    # brokerage on record (Sat 07:35): no red-flag-like phone reason, but still not confirmed
    phone_cleared_by_licence: bool = False
    # A15: who is on record is a listing brokerage, not a manager with an office phone.
    brokerage_only: bool = False
    lookalike_link_flag: bool = False  # a link imitates the building's own website
    unit_flag: bool = False  # the unit is not on the record, or its bedrooms do not match
    license_flag: bool = False  # the ad prints a license number that is not an active license
    license_given_flag: bool = False  # the number the renter typed is not an active license
    owner_flag: bool = False  # says they are the owner; the owner of record is someone else
    # Someone at the office's own website domain on CoStar's record opened a one-time link for
    # this case. The domain, never an address. It stands in for phone_confirmed in VERIFIED
    # (Vidyut, Sat 09:38), and only together with the photos placed and nothing else holding.
    office_confirmed_domain: str | None = None
    # The office at that domain said the ad is NOT theirs. A reason that holds the case
    # (never a red flag, never DONT_PAY: it is an answer, not proof).
    office_declined_domain: str | None = None


class VerdictState(StrEnum):
    VERIFIED = "verified"
    HOLD = "hold"
    DONT_PAY = "dont_pay"  # always shown as "Don't pay · could not verify", never as "scam"
    UNVERIFIED = "unverified"


class Verdict(BaseModel):
    case_id: str
    state: VerdictState
    reasons: list[str]
    source: DataSource


# ---------------------------------------------------------------------------------------------
# Cross-lane module evidence (XO, Fri Nov 13 22:00).
#
# Each module hands verdict.py one of the shapes below. Fixtures for every shape live in
# fixtures/contracts/ and tests/test_contracts.py proves they parse, so every lane can build
# against them before the producing lane exists. Adding an optional field is fine in a lane PR;
# renaming or removing a field needs an issue first (AGENTS.md, "Shared contracts").
# ---------------------------------------------------------------------------------------------


class Pose(BaseModel):
    """Camera pose of a photo inside a Matterport model, in the model's own frame."""

    sweep_id: str | None = None
    position: tuple[float, float, float]
    rotation_quat: tuple[float, float, float, float]  # x, y, z, w
    fov_deg: float | None = None


class FloorPlanCandidate(BaseModel):
    """One building and floor plan the photos could belong to, with the evidence for it."""

    property_id: str  # our own id for the record (never an address)
    model_id: str
    floor_plan: str | None = None  # "2 bed / 2 bath"; model units, never a unit number
    photos_located: int
    total_inliers: int


class LocateResult(BaseModel):
    """locate/ (lane V) output for one case: every listing photo, placed or not."""

    case_id: str
    photos: list[PhotoLocation]
    claimed_property_id: str | None = None
    # True when the ad named no home and the scan identified it: claimed_property_id is then
    # the home the photos were placed in.
    identified_by_scan: bool = False
    identified_photos: int = 0  # photos that placed in that home on the strict bar
    chosen: FloorPlanCandidate | None = None
    alternatives: list[FloorPlanCandidate] = Field(default_factory=list)
    poses: dict[str, Pose] = Field(default_factory=dict)  # photo_id -> pose, located photos only
    thresholds_version: str  # hash or tag of thresholds.toml used


class SpotResult(BaseModel):
    """One spot of the presence challenge (two-step: 10 min, then 90 s)."""

    spot_id: str
    step: int = Field(ge=1, le=2)
    revealed_at: datetime
    deadline_s: int  # 600 for step 1, 90 for step 2
    replied_at: datetime | None = None
    reply_photo_id: str | None = None
    code_read: bool | None = None  # local OCR matched the drawn code
    located: bool | None = None  # reply placed at this spot in the twin
    inliers: int | None = None


class ChallengeResult(BaseModel):
    """challenge/ (lane D) output. `presence` is the only field verdict.py may lift from it."""

    case_id: str
    challenge_id: str
    code: str = Field(min_length=4, max_length=4)
    spots: list[SpotResult]
    retries: int = Field(default=0, ge=0, le=2)
    presence: PresenceStatus
    injection_text_seen: bool = False  # paper held text other than the code; logged, ignored


class RecaptureLabel(StrEnum):
    GENUINE = "genuine"
    SCREEN = "screen"  # photo of a screen
    PRINT = "print"  # photo of a printout
    PASTE = "paste"  # code digitally pasted in
    UNKNOWN = "unknown"


class RecaptureResult(BaseModel):
    """recapture/ (lane V) output for one reply photo. It can only block a pass, never accuse."""

    photo_id: str
    label: RecaptureLabel
    score: float = Field(ge=0.0, le=1.0)  # calibrated probability the photo is not genuine
    blocks_pass: bool  # score over the frozen threshold
    model_version: str  # "v0", "v1", ... or "off" when RECAPTURE_MODEL is not on


class MemoryHitKind(StrEnum):
    NONE = "none"
    SAME_CASE_LISTING = "same_case_listing"  # reply copies a listing photo of this case
    OTHER_CHECK = "other_check"  # seen in another check; never reveal which


class MemoryResult(BaseModel):
    """memory/ (lane V) output for one photo. Hashes only, no pixels kept, 7-day TTL."""

    photo_id: str
    hit: MemoryHitKind
    method: str  # "phash", "dhash", "embedding"
    distance: float | None = None
    matched_listing_photo_id: str | None = None  # SAME_CASE_LISTING only
    first_seen_on: date | None = None  # OTHER_CHECK only; a date, never a case id


class RuleCategory(StrEnum):
    PAYMENT_METHOD = "payment_method"  # Zelle, wire, gift card, crypto before a viewing
    FEE_ASK = "fee_ask"  # application or holding fee to a person before a viewing
    DATA_ASK = "data_ask"  # SSN, bank login or ID before a viewing
    PRESSURE = "pressure"  # urgency, "many people interested", abroad story
    LINK = "link"  # payment or lease link from the poster


class RuleHit(BaseModel):
    """One code-owned rule that fired (agent/rules, lane A). Card text comes from the rule id."""

    rule_id: str  # e.g. "payment.zelle_before_viewing"
    category: RuleCategory
    red_flag: bool
    lang: str = "en"
    evidence_span: str | None = None  # the renter's own text that fired it, never sponsor data


class PriceStatus(StrEnum):
    WITHIN_RANGE = "within_range"
    BELOW_RANGE = "below_range"  # never DONT_PAY on its own; concessions happen
    NOT_CHECKED = "not_checked"  # no rent in our data for this building


class UnitStatus(StrEnum):
    """Is the unit the listing names on the building's record, with those bedrooms? (A7)"""

    ON_RECORD = "on_record"
    NOT_ON_RECORD = "not_on_record"  # the record lists units, and this one is not among them
    BEDS_MISMATCH = "beds_mismatch"  # the unit or its floor plan has a different bedroom count
    NOT_CHECKED = "not_checked"  # the listing names no unit or beds, or the record has neither


class PriceResult(BaseModel):
    """Rent vs record (lane A rules, from lane D's record), plus refund-the-difference input."""

    status: PriceStatus
    listed_rent: int | None = None  # whole dollars per month, from the renter's listing
    record_median: int | None = None
    record_min: int | None = None
    record_max: int | None = None
    n_floor_plans: int | None = None
    # A7 (#67): the unit on the record, and the per-bed guard.
    unit: UnitStatus = UnitStatus.NOT_CHECKED
    per_bed: bool = False  # the record prices by the bed, so the rent was not compared
    compared_beds: int | None = None  # the rent was compared with floor plans of this size


class PhoneMatch(StrEnum):
    """Is the phone number in the listing the leasing office on the record? (A7)"""

    YES = "yes"
    NO = "no"  # both sides have a number and they differ
    NOT_CHECKED = "not_checked"  # the listing or the record has no number


class LinkDomain(StrEnum):
    """How a link in the listing compares with the building's own website. (A7)"""

    MATCHES = "matches"  # the building's own site, or a page under it
    LOOKALIKE = "lookalike"  # close to it but not it: a typo, punycode, extra words
    OTHER = "other"  # some other site; says nothing either way
    NOT_CHECKED = "not_checked"  # the listing has no link, or the record has no website


class AuthorityResult(BaseModel):
    """Manager-on-record yes/no. Company names only, never a person or a phone number."""

    status: AuthorityStatus
    manager_on_record: str | None = None  # company name, or None when the record has none
    poster_said: str | None = None  # what the renter typed the poster claimed
    # A7 (#67). Yes/no only: no phone number, hash or web address is ever kept here.
    office_phone_match: PhoneMatch = PhoneMatch.NOT_CHECKED
    link_domain: LinkDomain = LinkDomain.NOT_CHECKED
    # A15: the comparison was with the listing brokerages alone. The home has no property
    # record, so there is no manager, office phone or website on record to compare with.
    brokerage_only: bool = False


class ForSaleStatus(StrEnum):
    ACTIVE = "active"  # listed for sale right now
    RECENTLY_RENTED = "recently_rented"  # the record shows it was rented out recently
    NONE = "none"  # looked up, and neither


class ForSaleMatch(BaseModel):
    """D7 (lane D): the home posted as a rental, looked up in the for-sale listings we hold."""

    status: ForSaleStatus
    site: str = "Homes.com"  # where it is listed; shown on the card
    listed_on: date | None = None
    changed_on: date | None = None  # when it reached its current status
    # Listing offices on record (brokerage company names, Homes.com `offices[].name`). These
    # count as legitimate marketers. Companies only: an agent's personal name is never kept.
    offices: list[str] = Field(default_factory=list)


class LicenseStatus(StrEnum):
    LICENSED = "licensed"  # an active TREC license under the claimed name
    NOT_FOUND = "not_found"  # the license number in the ad is not an active Texas license
    NOT_CHECKED = "not_checked"  # no claim, no name, an owner's own home, or the lookup failed


class LicenseResult(BaseModel):
    """D10 (lane D, #128): the poster's real estate license claim, looked up in TREC.

    Never keeps the license number or any person's name (the poster's, or an individual
    sponsoring broker's)."""

    status: LicenseStatus
    claimed_role: str | None = None  # "agent", "broker" or "locator", from the poster's words
    sponsor_broker: str | None = None  # LICENSED only, and only when the sponsor is a company
    state: str = "TX"
    # Where the number that was looked up came from: "ad" (the listing printed it), "renter"
    # (the renter typed it when asked, A24 stretch), or None (no number was looked up, so with
    # a claim and no number we may ask). Never the number. A renter's typed number is the
    # renter's own thread: it never reaches the report pack and never reads as a fact about the ad.
    number_from: Literal["ad", "renter"] | None = None


class OwnerKind(StrEnum):
    COMPANY = "company"  # a company or institution: LLC, REIT, iBuyer, brokerage, trust company
    PERSON = "person"  # an individual. The card says "a private owner"; the name stays in lane D


class OwnerMatch(StrEnum):
    YES = "yes"
    NO = "no"
    NOT_CHECKED = "not_checked"


class PublishedRule(BaseModel):
    """A rule a company publishes about where it takes applications and money, quoted (A19).

    From lane A's table of verified rows. It travels with the case, so a recorded case is
    redrawn with the rule it had."""

    company: str  # the company, as it names itself
    rule: str  # its own words, quoted
    source_url: str  # where it is published
    checked_on: date  # the day one of us read it there


class OwnerResult(BaseModel):
    """The owner of record of the home the listing claims (D12, #130), and how the poster
    compares (A19, #125). Never a person's name, anywhere."""

    kind: OwnerKind
    company: str | None = None  # COMPANY only. A company name, never a person's
    # COMPANY only: the name is one we already know (a row in the published-rule table, or an
    # office on record in the kit). `company` is set only then; any other company is shown
    # as "a company owner", with no name (conductor ruling, round 5 on #160).
    company_known: bool = False
    # Does what the poster calls themselves match the owner of record? Yes or no, nothing
    # more. For a person owner lane D compares inside its adapter and sends only this.
    poster_matches: OwnerMatch = OwnerMatch.NOT_CHECKED
    poster_says_owner: bool = False  # lane A: the poster's own words say they are the owner
    published_rule: PublishedRule | None = None  # lane A: the owner's own rule, if verified


class AdNote(BaseModel):
    """One ad-vs-record line, as facts. The words live in card/strings.py (`claims.<key>`).

    `claim` names what the ad says (a `ClaimKind` value). `record` holds word keys for what
    the record says (floor kinds and the like). `year` and `number` carry a date or a count.
    `matches` is True for the one quiet confirming line. It carries no flag and holds no case.
    """

    key: str
    claim: str
    matches: bool = False
    pretext: bool = False  # the ad explains why nothing can be seen (new management, away...)
    record: list[str] = Field(default_factory=list)
    year: int | None = None
    ad_value: str | None = None
    record_value: str | None = None


class ModuleEvidence(BaseModel):
    """Everything the modules produced for one case. Lane A flattens it into Evidence (A1)."""

    case_id: str
    source: DataSource
    locate: LocateResult | None = None
    challenge: ChallengeResult | None = None
    recapture: list[RecaptureResult] = Field(default_factory=list)
    memory: list[MemoryResult] = Field(default_factory=list)
    rules: list[RuleHit] = Field(default_factory=list)
    price: PriceResult | None = None
    authority: AuthorityResult | None = None
    for_sale: ForSaleMatch | None = None  # D7; None means not looked up
    license: LicenseResult | None = None  # D10; None means not looked up
    # D12 + A19; None means no owner data (LA, an unknown address, or not looked up)
    owner: OwnerResult | None = None
    # A10: where price, authority and for_sale came from, when the record is real and the
    # rest of the case is not. None means "the same as `source`".
    record_source: DataSource | None = None
    # The record's own kind of home ("house", "multifamily"), when there is a record. The
    # card says "this home" about a house and "this building" otherwise. It changes no state.
    property_type: str | None = None
    # A14: a reply came, could not be accepted, and no further photo will be asked for. The
    # card then says "we could not confirm", not "ask for a new photo". It changes no state.
    no_retry_left: bool = False
    # The domain, from CoStar's record, through which the office confirmed this case with a
    # one-time link (snapback.office). None means nobody did.
    office_confirmed_domain: str | None = None
    # The office at that domain said the ad is NOT theirs. A reason that holds the case
    # (never a red flag, never DONT_PAY: it is an answer, not proof).
    office_declined_domain: str | None = None
    # Ad vs record: what the ad claims against what CoStar's record says. Information only; no
    # verdict reads it. Empty means nothing to say (a record that is silent is not a finding).
    ad_notes: list[AdNote] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# Card (what S3, the PNG card and iMessage render) and the SSE trace (S2 trace panel).
# ---------------------------------------------------------------------------------------------


class CardRowKind(StrEnum):
    PLACE = "place"
    PERSON = "person"
    PRICE = "price"
    # Ad vs record: info lines only, drawn after PRICE and only when there is something to say.
    CLAIMS = "claims"


class CardTone(StrEnum):
    """Colour never carries meaning alone: every tone also has words on the line."""

    OK = "ok"
    HOLD = "hold"
    RED_FLAG = "red_flag"
    NOT_SHOWN = "not_shown"
    NOT_CHECKED = "not_checked"


class CardLine(BaseModel):
    label: str  # "Here now", "Allowed to rent it", "Payment ask", "Rent vs record"
    text: str  # code-owned string from the string table, never model output
    tone: CardTone
    # A10: where this line's facts came from, when that differs from the card as a whole. A
    # card can hold lines from a real record beside stand-ins for the twin and the challenge.
    # None means "the same as the card".
    source: DataSource | None = None


class CardRow(BaseModel):
    kind: CardRowKind
    lines: list[CardLine]


class Card(BaseModel):
    case_id: str  # short public id, e.g. "7Q2M"
    source: DataSource
    state: VerdictState
    checked_at: datetime
    expires_at: datetime
    rows: list[CardRow]  # PLACE, PERSON, PRICE always; CLAIMS after them only when it has a line
    not_checked: list[str]  # "ID", "lease", "ownership"
    footer: list[str]
    verify_url: str | None = None
    lang: str = "en"
    # A7 (#67): set when the home is listed for sale or was rented recently, so the web can
    # draw the dates as a history strip. The sentence about it is a PLACE line like any other.
    for_sale: ForSaleMatch | None = None


class ChoiceKind(StrEnum):
    """The agent's five bounded choices (v3.1 section 6)."""

    WHICH_CHECKS = "which_checks"
    WHICH_FLOOR_PLAN = "which_floor_plan"
    WHICH_SPOT = "which_spot"
    RETRY_OR_STOP = "retry_or_stop"
    ASK_HUMAN = "ask_human"
    NEXT_CHECK = "next_check"  # A24: which evidence-gated check to run next (order only)
    NEXT_SEARCH = "next_search"  # E1: which retry search to spend on an unplaced photo
    WHICH_PHOTO = "which_photo"  # E1: which unplaced photo gets the short search budget
    DWELL_ROOMS = "dwell_rooms"  # E5: which rooms of the walk open expanded (walk sub-agent, D3)
    LEAD_CHECKS = "lead_checks"  # E5: which checks lead the summary and tour request (D4)


class TraceKind(StrEnum):
    CHOICE = "choice"  # one of the five choices, with options, pick and reason
    TOOL = "tool"  # a tool call started or finished
    STATUS = "status"  # waiting for a reply, timer running
    HITL = "hitl"  # waiting for the renter to approve
    VERDICT = "verdict"  # decide() ran; payload carries the state
    ERROR = "error"
    # E0: the deep agent's own steps, bridged from its stream (never invented by the trace)
    TODO = "todo"  # the agent's todo list was written or changed
    AGENT = "agent"  # a hand-off to a sub-agent started or returned (name in `pick`)
    FILE = "file"  # a file was written in the agent's file system (path in `pick`)
    UNSURE = "unsure"  # code-raised: a measured thing is close to or past a line


class TraceEvent(BaseModel):
    """One line of the agent trace, sent as SSE `event: trace` with this JSON as `data`."""

    case_id: str
    seq: int = Field(ge=0)  # strictly increasing per case; the client drops repeats
    at: datetime
    kind: TraceKind
    choice: ChoiceKind | None = None  # CHOICE only
    options: list[str] = Field(default_factory=list)
    pick: str | None = None
    reason: str  # one plain sentence; may be model-written, never sets a state
    source: DataSource
    # A24: who made this step happen. "model" only when a language model picked from the
    # code-written options; everything else (the code policy, a fallback, a tool code ran,
    # a random draw, the renter's own answer) is "policy".
    chosen_by: Literal["model", "policy"] = "policy"


# ---------------------------------------------------------------------------------------------
# Data handed between lanes before verdict time (XO, Fri Nov 13 22:10).
# ---------------------------------------------------------------------------------------------


class SpotCandidate(BaseModel):
    """One fixed-structure spot (window frame, door, built-in) a challenge may name."""

    spot_id: str
    model_id: str
    label: str  # plain words the renter reads: "the north window frame in the living room"
    pose: Pose
    inliers: int  # how well the scan matches at this spot; higher ranks first
    overlaps_listing_photo: bool  # True means excluded from the draw


class SpotRanking(BaseModel):
    """locate/ (lane V) output that challenge/ (lane D) draws from: top 5, at random."""

    case_id: str
    model_id: str
    floor_plan: str | None = None
    spots: list[SpotCandidate]  # ranked best first


class FloorPlanRent(BaseModel):
    """One floor plan on the record with its rent band (D7)."""

    name: str | None = None  # "2 bed / 2 bath"
    beds: int | None = None  # 0 for a studio
    rent_min: int | None = None  # whole dollars per month
    rent_max: int | None = None
    per_bed: bool = False  # priced per bed: never compare with a whole-unit rent
    baths: float | None = None  # search (council 4): bathrooms on the floor plan
    units_available: int | None = None  # units CoStar reported available at its last research


class UnitOnRecord(BaseModel):
    """One unit the record lists for the building (D7)."""

    unit: str  # as the record writes it: "4B", "305"
    beds: int | None = None
    floor_plan: str | None = None


class PropertyRecord(BaseModel):
    """CoStar adapter (lane D) output. Our own id, never an address in fixtures or tests."""

    property_id: str
    source: DataSource
    market: str | None = None
    property_type: str | None = None
    floors: int | None = None
    year_built: int | None = None
    lat: float | None = None
    lon: float | None = None
    model_ids: list[str] = Field(default_factory=list)
    floor_plans: list[str] = Field(default_factory=list)
    manager_company: str | None = None  # company only, and only if the probe finds the field
    rent_min: int | None = None
    rent_median: int | None = None
    rent_max: int | None = None
    # D7 fields, stubbed by A7 (#67). All optional; an empty list means the record has none.
    # The leasing office's phone is never stored as digits. This is
    # snapback.agent.rules.contact.phone_hash(number, phone_salt()), a keyed hash.
    site_phone_hash: str | None = None
    website_host: str | None = None  # the building's own site, host only: "oakcourt.example"
    # Shown only to the office, in the confirm email and page, so it can tell which ad this is.
    building_name: str | None = None
    street_address: str | None = None
    floor_plan_rents: list[FloorPlanRent] = Field(default_factory=list)
    units: list[UnitOnRecord] = Field(default_factory=list)
    # Search (council 4): building facts for must-haves. None means the record does not say.
    is_walkup: bool | None = None
    has_elevator: bool | None = None  # True only when an elevator is on record
    metering: str | None = None  # "individual" or "master"
    parking_ratio: float | None = None  # spaces per unit, as reported
    # What the ad can be held to (ad vs record). Derived words and numbers only, never a
    # photo, a caption or a sentence from the kit. Empty or None means the record does not say.
    floors_photos: list[str] = Field(default_factory=list)  # "wood", "carpet", "tile", "laminate"
    floor_photo_count: int = 0  # photos whose labels name a floor
    floors_listing: list[str] = Field(default_factory=list)  # the same words, from listing features
    laundry_listing: list[str] = Field(default_factory=list)  # "machine", "hookup", "room"
    pool_on_record: bool | None = None  # True: seen or listed; False: listed features name none
    parking_spaces: int | None = None
    yard_on_record: bool | None = None  # True only; the record never says "no yard"
    pets_ok: bool | None = None
    beds_range: tuple[int, int] | None = None
    baths_range: tuple[float, float] | None = None
    sqft_range: tuple[int, int] | None = None
    manager_since: date | None = None  # the latest start of a property manager on record
    sale_history_known: bool = False  # the record covers sales, so "no sale" is a finding
    last_sale: date | None = None


class AerialTile(BaseModel):
    """Vexcel adapter (lane D) output: one oblique tile, kept at most 7 days, never in git."""

    property_id: str
    source: DataSource
    direction: str  # "north", "east", "south", "west" or "nadir"
    captured_on: date | None = None
    path: str  # local file under data/ (or fixtures/ for the synthetic tile)


class AerialSideOut(BaseModel):
    """One building in the aerial proof (D9, approved on #41)."""

    tile: AerialTile | None = None  # None: no tile (no coverage, rate limited, out of time)
    record: PropertyRecord | None = None  # building facts and company names only
    image_url: str | None = None  # our own route; never a Vexcel URL, the key stays server side


class AerialProofResponse(BaseModel):
    """`GET /cases/{case_id}/aerial`: the claimed building and the one the photos matched."""

    case_id: str
    source: DataSource
    claimed: AerialSideOut
    matched: AerialSideOut | None = None  # a photo located_elsewhere; None otherwise
    distance_m: float | None = None  # None when either record lacks lat/lon


# ---------------------------------------------------------------------------------------------
# The "Report this copy" pack (A20): what a listing agent takes to the platform.
# ---------------------------------------------------------------------------------------------


class ReportPlatform(StrEnum):
    FACEBOOK = "facebook"
    ZILLOW = "zillow"
    CRAIGSLIST = "craigslist"


class ReportStatusStrip(BaseModel):
    """What the home's own record says. The same facts the card already carries in `for_sale`."""

    status: ForSaleStatus
    site: str  # where the record is listed, e.g. Homes.com
    listed_on: date | None = None
    changed_on: date | None = None
    brokerage: str | None = None  # the listing office on record. A company, never a person


class ReportPhotoPair(BaseModel):
    """One listing photo something was found about. Pictures are references to OUR routes."""

    listing_photo: int  # which listing photo, counting from 1
    finding: str  # the fixed sentence for what was found about it
    listing_image_url: str | None = None  # our route for the photo as posted, when one exists
    match_image_url: str | None = None  # our route for the matching view, when one exists


class ReportSteps(BaseModel):
    platform: ReportPlatform
    name: str  # "Facebook Marketplace", "Zillow", "Craigslist"
    steps: list[str]  # what to click, in order, in the pack's language


class ReportResponse(BaseModel):
    """`GET /cases/{case_id}/report`: one pack for reporting a copied listing to a platform.

    Listing facts only. No score, count or threshold; no hash or model id; no image bytes;
    nothing about the renter; no word about any person."""

    case_id: str  # short public id
    source: DataSource
    lang: str
    checked_at: datetime
    state: VerdictState
    # True only on proof (DONT_PAY) or a record that shows the home for sale. Not on a hold
    # for something that is merely not confirmed: the poster may be a real agent.
    reportable: bool
    status_strip: ReportStatusStrip | None = None
    proof_lines: list[str]  # decide()'s own reasons, in order. Never model text
    photo_pairs: list[ReportPhotoPair] = Field(default_factory=list)
    twin_url: str | None = None  # our /case/{id}/twin page, where each photo was placed
    aerial_url: str | None = None  # our /cases/{id}/aerial route, when the case names a building
    platforms: list[ReportSteps] = Field(default_factory=list)
    not_checked: list[str]  # the card's standing list: what this does not show


# ---------------------------------------------------------------------------------------------
# Starting a case over HTTP (lane A's API; the upload page and the iMessage sidecar call it).
# ---------------------------------------------------------------------------------------------


class CaseProgress(StrEnum):
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"  # a challenge is drafted; the renter decides
    # A14: the challenge was sent and the poster's reply photo has not come, or another is
    # asked for. The card reads HOLD meanwhile: no reply is never a failure.
    WAITING_FOR_REPLY = "waiting_for_reply"
    # A24 stretch: the agent asked the renter for the license number the ad did not give.
    WAITING_FOR_ANSWER = "waiting_for_answer"
    DONE = "done"


class CreateCaseRequest(BaseModel):
    """`POST /cases`, sent as multipart form data. `photos` are files and are not in this model."""

    link: str | None = None  # the listing's link; read as text, never fetched
    text: str | None = None  # the listing text or the poster's messages, as the renter has them
    renter_id: str | None = None  # set by the iMessage sidecar; the web app sends none
    # A10: our id for the building the listing claims to be in. With none, there is no record
    # to compare the listing with.
    property_id: str | None = None


class CreateCaseResponse(BaseModel):
    """What `POST /cases` returns. This is the only time the case's secrets are shown."""

    case_id: str  # short public id, for display and for reading the case
    source: DataSource
    token: str  # write secret for this case; send it on every write, in a header only
    # Read-only secret: opens the trace, the challenge text, the report and the aerial proof.
    # Header only, like the write secret; never in the address (locked, Sat 02:27).
    read_token: str | None = None
    status: CaseProgress
    state: VerdictState | None = None  # set once the case is done
    challenge_text: str | None = None  # the message the renter may forward; None if none drafted
    photos: int = 0
    screenshots: int = 0  # images that were read as text
    injection_noticed: bool = False  # the listing had text written for an AI system


# ---------------------------------------------------------------------------------------------
# The poster's reply (A14, lane A's API; the upload page and the iMessage sidecar call it).
# ---------------------------------------------------------------------------------------------


class ReplyCheck(StrEnum):
    """What checking one reply photo found. Each is a fact about the photo, not about a person."""

    # One of the listing's own photos: forged, whenever it arrives. The only proof here.
    COPY_OF_LISTING_PHOTO = "copy_of_listing_photo"
    # The code could not be read on the photo (wrong, missing or unreadable). Not confirmed,
    # ask again up to the retry cap, then HOLD. Never forged: it is not proof.
    CODE_NOT_READ = "code_not_read"
    # It came after the deadline and is not a copy, so it was not counted. Asked again once.
    LATE = "late"
    # The code is there and the photo is not a copy, but nothing has checked that it was taken
    # at the spot (that needs locate, V2). Not confirmed, never proven.
    CODE_READ_SPOT_NOT_CHECKED = "code_read_spot_not_checked"
    ASK_AGAIN = "ask_again"  # not at the spot, or it looks like a photo of a screen: ask again
    NEXT_SPOT = "next_spot"  # the first spot matched; a second one is asked for
    PROVEN = "proven"  # both spots matched
    IGNORED = "ignored"  # the challenge is over; this photo changed nothing


class ReplyResponse(BaseModel):
    """What `POST /cases/{id}/reply` returns: the poster's reply photo, checked."""

    case_id: str  # short public id
    source: DataSource
    # While another photo is wanted this is waiting_for_approval: the next message is in
    # `challenge_text` for the renter to approve. It is waiting_for_reply once that is sent,
    # and done when nothing more will be asked.
    status: CaseProgress
    check: ReplyCheck
    presence: PresenceStatus
    state: VerdictState | None = None  # set once the case is done
    # The next message for the renter to forward, when another photo is asked for.
    challenge_text: str | None = None


# ---------------------------------------------------------------------------------------------
# Search (council 4 core): a renter's brief in, CoStar's researched places out.
# ---------------------------------------------------------------------------------------------

AS_OF = "as of CoStar's last research"


class RenterBrief(BaseModel):
    """What the renter asked for. Every field is optional; code filters on what is given."""

    max_rent_month: int | None = Field(default=None, ge=0, le=1_000_000)  # whole unit, a month
    beds_min: int | None = Field(default=None, ge=0, le=20)  # 0 is a studio
    baths_min: float | None = Field(default=None, ge=0, le=20)
    needs_no_walkup: bool = False
    needs_parking: bool = False
    pets: bool = False
    move_in_by: date | None = None
    max_results: int = Field(default=10, ge=1, le=50)


class RentalHouse(BaseModel):
    """One active house rental from the Homes.com records in the kit (search supply)."""

    property_id: str
    source: DataSource
    beds: int | None = None
    baths: float | None = None
    rent_min: int | None = None  # as listed, whole dollars a month
    rent_max: int | None = None
    pets_ok: bool | None = None  # None: the record does not say
    parking_spaces: int | None = None
    available_on: date | None = None
    office: str | None = None  # the listing office, company name only
    has_scan: bool = False


class BudgetFit(StrEnum):
    WITHIN = "within"  # the whole reported price range is at or under the budget
    STARTS_WITHIN = "starts_within"  # the low end fits, the high end does not
    NO_FULL_PRICE = "no_full_price"  # one end of the price is missing: not counted as within
    NO_BUDGET = "no_budget"  # the brief gave no budget


class MustHaveLine(BaseModel):
    key: str  # "walkup", "parking", "pets", "utilities"
    text: str
    met: bool | None = None  # None: the record does not say


class PlaceMatch(BaseModel):
    property_id: str
    kind: Literal["apartment", "house"]
    floor_plan: str | None = None  # "2 bed / 2 bath" for an apartment, None for a house
    # Stable id of this plan within its building (label, price ends, units): many plans share a
    # label, so a pick is made by this key, never by the label alone.
    plan_key: str | None = None
    beds: int | None = None
    baths: float | None = None
    rent_min: int | None = None  # the asking price as reported, for code to compare
    rent_max: int | None = None
    budget_fit: BudgetFit
    price_text: str
    availability_text: str
    must_haves: list[MustHaveLine] = Field(default_factory=list)
    musts_met: int = 0
    has_3d_scan: bool = False
    scan_text: str | None = None  # "a 3D scan in this building"
    office_on_record: str | None = None  # company name only
    # True only for a place that got the record-side deep check (the model picks up to three
    # per search); every other place is "researched" only. The line is built by code from the
    # record, so it is the same for the same place whoever chose it.
    checked: bool = False
    check_line: str | None = None
    source: DataSource


class SearchDecision(BaseModel):
    """One choice the search agent made, in the trace's own shape. `chosen_by` is "model" only
    when a language model picked from the options code wrote; a menu of one is always "policy"."""

    kind: Literal["deep_check", "tradeoff", "tour_gate"]
    options: list[str]
    pick: str
    reason: str
    chosen_by: Literal["model", "policy"]


class CasePreferences(BaseModel):
    """What the agent remembers about one renter's session. Code-defined keys only: a rejected
    walk-up, a parking need, a lower budget, places to stop showing. Never free text."""

    no_walkup: bool = False
    needs_parking: bool = False
    max_rent: int | None = Field(default=None, ge=0, le=1_000_000)
    avoid_property_ids: list[str] = Field(default_factory=list, max_length=50)
    # M9: orders the list (3D-scan places first), never filters it.
    prefer_scans: bool = False


class PreferencesUpdate(BaseModel):
    """`POST /cases/{id}/preferences`: the renter rejected something. Each field is optional."""

    model_config = ConfigDict(extra="forbid")

    no_walkup: bool | None = None
    needs_parking: bool | None = None
    max_rent: int | None = Field(default=None, ge=0, le=1_000_000)
    avoid_property_id: str | None = Field(default=None, min_length=1, max_length=64)
    prefer_scans: bool | None = None


class SearchResponse(BaseModel):
    source: DataSource
    as_of: str = AS_OF
    n_considered: int  # priced places looked at before the brief's filters
    n_matches: int  # places that passed, before max_results cut the list
    matches: list[PlaceMatch]
    # What the agent decided, in order, each stamped model or policy with a reason.
    decisions: list[SearchDecision] = Field(default_factory=list)
    question: str | None = None  # the one trade-off question to put to the renter
    ask_first: bool = False  # ask it before drafting a tour request
    remembered: list[str] = Field(default_factory=list)  # preference keys applied to this search


class AlternativesResponse(BaseModel):
    case_id: str
    source: DataSource
    as_of: str = AS_OF
    matches: list[PlaceMatch]
    decisions: list[SearchDecision] = Field(default_factory=list)
    question: str | None = None
    ask_first: bool = False
    remembered: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# M9: the finder, a deep agent that learns from what the renter picks and passes on and offers
# what to remember. Nothing it learns applies until the renter accepts (plan/map-plan.md 4).
# ---------------------------------------------------------------------------------------------

FinderProposalKey = Literal[
    "propose_no_walkup", "propose_parking", "propose_prefer_scans", "propose_lower_budget"
]


class FinderSessionStarted(BaseModel):
    """`POST /finder/sessions`. The write token is shown once; later calls send it in a header."""

    session_id: str
    token: str
    source: DataSource
    mode: Literal["policy", "deepagents"]


class FinderSignal(BaseModel):
    """One thing the renter did. Attributes of the place only: which place never leaves."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick", "pass", "brief"]
    place_kind: Literal["apartment", "house"] | None = None
    has_scan: bool | None = None
    rent_from: int | None = Field(default=None, ge=0, le=1_000_000)
    walkup: bool | None = None
    parking: bool | None = None
    brief_field: Literal["budget", "beds", "parking", "no_walkup", "pets"] | None = None
    rent_max: int | None = Field(default=None, ge=0, le=1_000_000)


class FinderMessageRequest(BaseModel):
    """`POST /finder/{session}/message`. Code reads the text into signals; the main agent sees
    only the cleaned words (phones, emails, links and addresses removed, 500 characters)."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=500)
    signals: list[FinderSignal] = Field(default_factory=list, max_length=20)


class FinderProposal(BaseModel):
    """Something the agent offers to remember. `update` changes nothing until accepted."""

    id: str
    key: FinderProposalKey
    update: PreferencesUpdate
    text: str  # the question put to the renter, written by code
    evidence: str  # the count it rests on, e.g. "you passed on 3 of 3 walk-ups"
    reason: str  # one plain sentence from whoever chose it
    chosen_by: Literal["model", "policy"]
    status: Literal["proposed", "accepted", "declined"] = "proposed"
    at: datetime


class FinderPick(BaseModel):
    """One lead pick. `line` is built by code from the record; `why` is one sentence from the
    search sub-agent (`chosen_by`), kept only if it passes the same cleaning as every note."""

    pid: str
    rank: int = Field(ge=1)
    kind: Literal["apartment", "house"]
    has_scan: bool
    line: str
    why: str
    chosen_by: Literal["model", "policy"]
    as_of: str = AS_OF
    # The record's facts behind the line, so the Finder tab can send a pass or a pick back as a
    # signal (attributes only). Shown to the renter; never shown to a model.
    rent_from: int | None = None
    walkup: bool | None = None
    parking: bool | None = None


class FinderNote(BaseModel):
    path: str  # /finder/<session>/prefs.md or picks.md
    text: str
    written_by: Literal["model", "policy"]


class FinderTraceEvent(BaseModel):
    """The finder's trace, in the same shape as a case's, for the same agent rail."""

    session_id: str
    seq: int = Field(ge=0)
    at: datetime
    kind: TraceKind
    options: list[str] = Field(default_factory=list)
    pick: str | None = None
    reason: str
    source: DataSource
    chosen_by: Literal["model", "policy"] = "policy"


class FinderReply(BaseModel):
    session_id: str
    source: DataSource
    mode: Literal["policy", "deepagents"]
    reply: str
    reply_by: Literal["model", "policy"]
    proposals: list[FinderProposal]  # the new ones this turn
    picks: list[FinderPick]
    as_of: str = AS_OF


class FinderWatchRequest(BaseModel):
    """`POST /finder/{session}/watch`. iMessage is the one channel (M10, ruling R-M1)."""

    model_config = ConfigDict(extra="forbid")

    channel: Literal["imessage"]


class FinderWatchStatus(BaseModel):
    """A watch on a finder session: recorded once, with the `watch_added` event it published."""

    session_id: str
    channel: Literal["imessage"]
    kind: Literal["brief"] = "brief"  # it watches the session's brief, never one place
    event_id: str
    source: DataSource
    at: datetime


class FinderState(BaseModel):
    """`GET /finder/{session}/state`: everything the Finder tab shows."""

    session_id: str
    source: DataSource
    mode: Literal["policy", "deepagents"]
    applied: CasePreferences
    proposals: list[FinderProposal]  # all of them, with status
    picks: list[FinderPick]
    learned: dict[str, str | bool]  # "what I've learned about you": fact key to "3 of 3" or yes/no
    notes: list[FinderNote]
    trace: list[FinderTraceEvent]
    as_of: str = AS_OF
    watch: FinderWatchStatus | None = None  # set by `POST /finder/{session}/watch`


class FinderDecision(BaseModel):
    """`POST /finder/{session}/proposals/{id}`."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "decline"]


class TourDraftRequest(BaseModel):
    property_id: str = Field(min_length=1, max_length=64)
    floor_plan: str | None = Field(default=None, max_length=64)
    plan_key: str | None = Field(default=None, max_length=128)
    brief: RenterBrief | None = None


class TourDraft(BaseModel):
    """A draft for the renter to approve. Nothing is sent; there is no send route."""

    property_id: str
    addressee: str  # the office on record, company name only
    text: str
    status: Literal["draft"] = "draft"
    sent: Literal[False] = False
    source: DataSource


# ---------------------------------------------------------------------------------------------
# E0: the evidence file (plan/ml-agent-plan.md 3b). Written by code only, read by the card, the
# "How we know" drawer and the walk. A model never sees `points`; it is stripped before any
# chooser payload (allow-list test in E6).
# ---------------------------------------------------------------------------------------------


class PlaceStep(BaseModel):
    """One search spent on one photo: the base search, or a retry the place sub-agent picked."""

    option: str  # "base", "focus_scan:S2", "wider_index", "deeper_claimed" or "stop"
    chosen_by: Literal["model", "policy"]  # "base" is always policy; a menu of one is policy
    seconds: float | None = None
    result: Literal["placed", "not_placed", "elsewhere", "skipped"]


class EvidencePoints(BaseModel):
    """Matched points for the drawing. A sample: `n_total` says how many matched in all."""

    n_total: int = Field(ge=0)
    # Pairs (ad x, ad y, scan x, scan y), each normalised to 0..1. At most 48.
    sampled: list[tuple[float, float, float, float]] = Field(default_factory=list, max_length=48)


class EvidencePhoto(BaseModel):
    alias: str  # "P1", "P2", ...: what a model and the drawer call the photo
    status: LocateStatus
    inliers: int | None = None
    inlier_ratio: float | None = None
    spread: float | None = None
    rival_ratio: float | None = None
    bar_failed: Literal["inliers", "ratio", "spread", "ambiguity"] | None = None
    room_label: str | None = None
    scan_alias: str | None = None  # "S1", "S2": the scan it was placed in
    stop_alias: str | None = None  # the walk stop it belongs to (W1), if any
    searches: list[PlaceStep] = Field(default_factory=list)
    points: EvidencePoints | None = None


class EvidenceFile(BaseModel):
    """`/evidence/photos.json`: every photo's measurements, the bars they were held to and
    which thresholds file those bars came from. Numbers shown on screen are read from here."""

    case_id: str
    source: DataSource
    thresholds_version: str
    bars: dict[str, float]  # e.g. {"min_inliers": 30, "min_inlier_ratio": 0.25, ...}
    photos: list[EvidencePhoto]
    written_by: Literal["code"] = "code"

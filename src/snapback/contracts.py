"""Shared data contracts between lanes.

Every lane reads and writes these shapes, so a change here can break three other lanes.
Change this file only through a pull request reviewed by the integrator lane.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DataSource(StrEnum):
    """Where a case's data came from. Every screen and every number shows this label."""

    LIVE = "live"
    FIXTURE = "fixture"


class LocateStatus(StrEnum):
    """Result of placing one listing photo in the 3D twins we have indexed."""

    LOCATED_IN_CLAIMED = "located_in_claimed"  # geometrically verified inside the claimed property
    LOCATED_ELSEWHERE = "located_elsewhere"  # verified inside a different indexed property
    NOT_LOCATED = "not_located"  # the claimed property is indexed and the photo matches nowhere
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
    lookalike_link_flag: bool = False  # a link imitates the building's own website
    unit_flag: bool = False  # the unit is not on the record, or its bedrooms do not match


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
    # A10: where price, authority and for_sale came from, when the record is real and the
    # rest of the case is not. None means "the same as `source`".
    record_source: DataSource | None = None
    # A14: a reply came, could not be accepted, and no further photo will be asked for. The
    # card then says "we could not confirm", not "ask for a new photo". It changes no state.
    no_retry_left: bool = False


# ---------------------------------------------------------------------------------------------
# Card (what S3, the PNG card and iMessage render) and the SSE trace (S2 trace panel).
# ---------------------------------------------------------------------------------------------


class CardRowKind(StrEnum):
    PLACE = "place"
    PERSON = "person"
    PRICE = "price"


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
    rows: list[CardRow]  # always PLACE, PERSON, PRICE in that order
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


class TraceKind(StrEnum):
    CHOICE = "choice"  # one of the five choices, with options, pick and reason
    TOOL = "tool"  # a tool call started or finished
    STATUS = "status"  # waiting for a reply, timer running
    HITL = "hitl"  # waiting for the renter to approve
    VERDICT = "verdict"  # decide() ran; payload carries the state
    ERROR = "error"


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
    floor_plan_rents: list[FloorPlanRent] = Field(default_factory=list)
    units: list[UnitOnRecord] = Field(default_factory=list)


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
# Starting a case over HTTP (lane A's API; the upload page and the iMessage sidecar call it).
# ---------------------------------------------------------------------------------------------


class CaseProgress(StrEnum):
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"  # a challenge is drafted; the renter decides
    # A14: the challenge was sent and the poster's reply photo has not come, or another is
    # asked for. The card reads HOLD meanwhile: no reply is never a failure.
    WAITING_FOR_REPLY = "waiting_for_reply"
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
    # Read-only secret: opens the trace and the challenge text, and may ride in `?token=`.
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

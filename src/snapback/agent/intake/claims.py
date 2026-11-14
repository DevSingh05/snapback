"""What an ad says about the home that a record can confirm or contradict (ad vs record).

A fixed vocabulary, in English and Spanish: floors, an in-unit washer and dryer, a pool, a
garage or parking, a yard, pets, beds, baths and square feet; and the pretext phrases a poster
uses to explain why the home cannot be seen ("under new management", "just sold", "the owner is
out of town", "I can't show it").

Conservative on purpose. A claim is found only when the ad says it plainly, and a denied claim
("no carpet", "not pet friendly", "washer and dryer not included") is not a claim. Words that
are about something else ("tile backsplash", "wood fence", "pool table", "street parking") do
not count. When unsure, no claim: a claim that is missed costs one quiet line, a claim that is
invented puts words in a poster's mouth.

Like `fields.py`, every quantifier is bounded and the text is bounded first (`normalise`),
because the poster wrote it. Nothing here reads a record.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from snapback.agent.intake.fields import extract_beds
from snapback.agent.rules.apply import normalise


class ClaimKind(StrEnum):
    FLOOR_WOOD = "floor_wood"
    FLOOR_CARPET = "floor_carpet"
    FLOOR_TILE = "floor_tile"
    FLOOR_LAMINATE = "floor_laminate"
    WASHER_DRYER = "washer_dryer"
    POOL = "pool"
    GARAGE = "garage"  # a garage, a driveway or a parking space that comes with the home
    YARD = "yard"
    PETS = "pets"
    BEDS = "beds"
    BATHS = "baths"
    SQFT = "sqft"
    # Pretext: ways to explain why nothing can be checked in person.
    NEW_MANAGEMENT = "new_management"
    NEW_OWNERSHIP = "new_ownership"
    JUST_SOLD = "just_sold"
    OWNER_AWAY = "owner_away"
    CANT_SHOW = "cant_show"


PRETEXT = frozenset(
    {
        ClaimKind.NEW_MANAGEMENT,
        ClaimKind.NEW_OWNERSHIP,
        ClaimKind.JUST_SOLD,
        ClaimKind.OWNER_AWAY,
        ClaimKind.CANT_SHOW,
    }
)


class AdClaim(BaseModel):
    kind: ClaimKind
    value: float | None = None  # beds, baths and square feet only


class AdClaims(BaseModel):
    claims: list[AdClaim] = Field(default_factory=list)

    def kinds(self) -> set[ClaimKind]:
        return {claim.kind for claim in self.claims}


MAX_MATCHES = 50  # per pattern: a hostile text cannot make this loop long
_FLAGS = re.IGNORECASE

# A clause ends at punctuation or a spaced dash: "No carpet, hardwood" denies only the carpet.
_CLAUSE_END = re.compile(r"[.,;:!?\n()\u2022|]|\s[-\u2013\u2014]\s")
_NEGATOR = re.compile(r"\b(?:no|not|without|never|non|sin)\b", _FLAGS)
# After the claim: "washer and dryer not included", "carpet-free", "no incluye".
_DENIED_AFTER = re.compile(
    r"^[\s-]{0,3}(?:(?:is|are|will be|was)\s{1,2})?"
    r"(?:not\b|\w{2,4}n['’]t\b|free\b|no\s{1,2}(?:incluy|incluid|se\b|est[aá]|permit|acept))",
    _FLAGS,
)


def _denied(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 40) : start]
    ends = list(_CLAUSE_END.finditer(before))
    clause = before[ends[-1].end() :] if ends else before
    if _NEGATOR.search(clause):
        return True
    return _DENIED_AFTER.match(text[end : end + 30]) is not None


class _Rule:
    """Patterns that say a claim, and what vetoes a match (words around it that change it)."""

    def __init__(
        self,
        kind: ClaimKind,
        patterns: list[str],
        *,
        before: str | None = None,
        after: str | None = None,
        deny: bool = True,
    ) -> None:
        self.kind = kind
        self.patterns = [re.compile(p, _FLAGS) for p in patterns]
        self.before = re.compile(before + r"$", _FLAGS) if before else None
        self.after = re.compile(r"^" + after, _FLAGS) if after else None
        self.deny = deny

    def found(self, text: str) -> bool:
        for pattern in self.patterns:
            for count, match in enumerate(pattern.finditer(text)):
                if count >= MAX_MATCHES:
                    break
                start, end = match.span()
                if self.before and self.before.search(text[max(0, start - 30) : start]):
                    continue
                if self.after and self.after.match(text[end : end + 30]):
                    continue
                if self.deny and _denied(text, start, end):
                    continue
                return True
        return False


_FAUX = r"(?:faux|fake|imitation|simulated)\s{1,2}"
_SHARED = (
    r"(?:community|shared|common|resort[- ]style|complex|building|club|neighbou?rhood|hoa|"
    r"apartment)\s{1,2}(?:\w{1,12}\s{1,2})?"
)

_RULES = [
    _Rule(
        ClaimKind.FLOOR_WOOD,
        [
            r"\bhard\s?woods?\b",
            r"\bwood(?:en)?\s{1,2}floor(?:s|ing)?\b",
            r"\bengineered\s{1,2}wood\b",
            r"\bparquet\b",
            r"\bpisos?\s{1,2}de\s{1,2}madera\b",
            r"\bmadera\s{1,2}(?:dura|s[oó]lida)\b",
        ],
        before=_FAUX,
        after=r"\s{0,2}(?:cabinet|door|fence|trim|blind|deck|counter|stair|furniture)",
    ),
    _Rule(
        ClaimKind.FLOOR_CARPET,
        [r"\bcarpet(?:ed|ing|s)?\b", r"\balfombra(?:s|do|da|dos|das)?\b"],
        before=_FAUX,
        after=r"\s{0,2}(?:clean|shamp)",
    ),
    _Rule(
        ClaimKind.FLOOR_TILE,
        [
            r"\b(?:ceramic|porcelain|stone|marble)?\s?tile[ds]?\s{1,2}floor(?:s|ing)?\b",
            r"\btile\s{1,2}throughout\b",
            r"\bfloors?\s{1,2}(?:are\s{1,2})?(?:in\s{1,2})?tile\b",
            r"\btiled\s{1,2}floors?\b",
            r"\b(?:ceramic|porcelain)\s{1,2}tile\b",
            r"\bpisos?\s{1,2}de\s{1,2}(?:azulejo|cer[aá]mica|loseta|porcelanato)\b",
        ],
        before=_FAUX + r"|wood[- ]look\s{1,2}",
        after=r"\s{1,2}(?:back\s?splash|shower|tub|counter|wall|surround)",
    ),
    _Rule(
        ClaimKind.FLOOR_LAMINATE,
        [
            r"\blaminate[sd]?\b",
            r"\bvinyl\s{1,2}plank\b",
            r"\bluxury\s{1,2}vinyl\b",
            r"\blvp\b",
            r"\bpiso\s{1,2}laminado\b",
            r"\blaminado\b",
        ],
        after=r"\s{1,2}(?:counter|cabinet|top\b|desk|shelv)",
    ),
    _Rule(
        ClaimKind.WASHER_DRYER,
        [
            r"\bwasher\s{0,2}(?:/|&|and|\+|,|or)?\s{0,2}dryer\b",
            r"\bw\s?/\s?d\b",
            r"\bin[- ](?:unit|home)\s{1,2}laundry\b",
            r"\blaundry\s{1,2}in[- ](?:unit|home)\b",
            r"\blavadora\s{1,2}(?:y|/)\s{1,2}secadora\b",
            r"\bsecadora\b",
            r"\blavadora\b",
        ],
        before=r"(?:shared|community|coin|on[- ]?site|common)\s{1,2}(?:\w{1,10}\s{1,2})?",
        after=r"\s{0,2}(?:hook\s?-?ups?|connections?|conexi[oó]n|conexiones)",
    ),
    _Rule(
        ClaimKind.POOL,
        [r"\bpool\b", r"\bpiscina\b", r"\balberca\b"],
        before=_SHARED,
        after=r"\s{1,2}(?:table|hall|party|side|cue)",
    ),
    _Rule(
        ClaimKind.GARAGE,
        [
            r"\bgarages?\b",
            r"\bgaraje\b",
            r"\bcochera\b",
            r"\bcarports?\b",
            r"\bdriveway\b",
            r"\b(?:off[- ]street|covered|reserved|assigned|private|free|included)\s{1,2}parking\b",
            r"\bparking\s{1,2}(?:for|included|available|space)",
            r"\bestacionamiento\s{1,2}(?:propio|privado|incluido|techado)\b",
        ],
        before=r"(?:street|guest|visitor|public)\s{1,2}",
        after=r"\s{1,2}(?:sale|only)\b",
    ),
    _Rule(
        ClaimKind.YARD,
        [
            r"\byards?\b",
            r"\bbackyard\b",
            r"\bpatio\s{1,2}trasero\b",
            r"\btraspatio\b",
            r"\bjard[ií]n\b",
            r"\bpatio\s{1,2}(?:grande|cercado|con\s{1,2}cerca)\b",
        ],
        before=r"(?:school|barn|junk|scrap|boat|church|brick|stock)\s{1,2}",
        after=r"\s{1,2}(?:sale|work)\b",
    ),
    _Rule(
        ClaimKind.PETS,
        [
            r"\bpet[- ]?friendly\b",
            r"\bpets?\s{1,2}(?:are\s{1,2})?(?:ok|okay|allowed|welcome|accepted|considered|permitted)\b",
            r"\b(?:cats?|dogs?)\s{1,2}(?:and\s{1,2}(?:cats?|dogs?)\s{1,2})?"
            r"(?:ok|okay|allowed|welcome|accepted)\b",
            r"\ballows?\s{1,2}pets\b",
            r"\bse\s{1,2}(?:aceptan|permiten)\s{1,2}mascotas\b",
            r"\bmascotas\s{1,2}(?:permitidas|bienvenidas|ok|aceptadas)\b",
            r"\bacept(?:a|amos)\s{1,2}mascotas\b",
            r"\bpermite\s{1,2}mascotas\b",
        ],
    ),
    _Rule(
        ClaimKind.NEW_MANAGEMENT,
        [
            r"\bnew\s{1,2}(?:property\s{1,2})?management\b",
            r"\bnew\s{1,2}property\s{1,2}manager\b",
            r"\bnueva\s{1,2}(?:administraci[oó]n|gerencia)\b",
        ],
    ),
    _Rule(
        ClaimKind.NEW_OWNERSHIP,
        [r"\bnew\s{1,2}(?:ownership|owners?)\b", r"\bnuevos?\s{1,2}due[ñn]os?\b"],
    ),
    _Rule(
        ClaimKind.JUST_SOLD,
        [
            r"\b(?:just|recently|newly)\s{1,2}sold\b",
            r"\b(?:just|recently)\s{1,2}(?:bought|purchased|acquired)\b",
            r"\bnewly\s{1,2}acquired\b",
            r"\breci[eé]n\s{1,2}(?:vendid[oa]|comprad[oa]|adquirid[oa])\b",
            r"\bacaba(?:mos)?\s{1,2}de\s{1,2}(?:comprar|vender)\b",
        ],
        after=r"\s{1,2}out\b",
    ),
    _Rule(
        ClaimKind.OWNER_AWAY,
        [
            r"\b(?:the\s{1,2})?owners?\s{1,2}(?:is\s{1,2}|are\s{1,2})?(?:currently\s{1,2})?"
            r"(?:out\s{1,2}of\s{1,2}(?:town|the\s{1,2}country|state)|away|overseas|abroad|"
            r"traveling|travelling|deployed)\b",
            r"\b(?:i\s{0,2}am|i['’]m|we\s{1,2}are|we['’]re)\s{1,2}(?:currently\s{1,2})?"
            r"(?:out\s{1,2}of\s{1,2}(?:town|the\s{1,2}country|state)|away|overseas|abroad|"
            r"traveling|travelling|deployed)\b",
            r"\bdue[ñn]o\s{1,2}(?:est[aá]\s{1,2})?(?:fuera|de\s{1,2}viaje|en\s{1,2}el\s{1,2}extranjero)",
            r"\bfuera\s{1,2}del\s{1,2}pa[ií]s\b",
            r"\bfuera\s{1,2}de\s{1,2}la\s{1,2}ciudad\b",
        ],
    ),
    _Rule(
        ClaimKind.CANT_SHOW,
        [
            r"\b(?:can['’]?t|cannot|can\s{1,2}not|unable\s{1,2}to|not\s{1,2}able\s{1,2}to|"
            r"won['’]?t\s{1,2}be\s{1,2}able\s{1,2}to)\s{1,2}(?:show|give\s{1,2}(?:a\s{1,2})?"
            r"(?:tour|showing)|meet)\b",
            r"\bno\s{1,2}(?:in[- ]person\s{1,2})?(?:showings?|tours?|viewings?)\b",
            r"\bno\s{1,2}(?:puedo|podemos)\s{1,2}(?:mostrar|ense[ñn]ar)\b",
            r"\bno\s{1,2}se\s{1,2}puede\s{1,2}(?:mostrar|ense[ñn]ar)\b",
        ],
        deny=False,
    ),
]

_BEDS_ES = re.compile(
    r"(?<![\w.$,])(\d{1,2})\s{0,3}-?\s{0,3}(?:rec[aá]maras?|habitaciones|dormitorios|cuartos)\b",
    _FLAGS,
)
_BATHS = re.compile(
    r"(?<![\w.$,])(\d{1,2}(?:\.5)?)\s{0,3}-?\s{0,3}(?:bath(?:room)?s?|ba\b|ba[ñn]os?)\b", _FLAGS
)
_SQFT = re.compile(
    r"(?<![$\d,.])(\d{1,2},\d{3}|\d{3,5})\s{0,2}"
    r"(?:sq\.?\s{0,2}ft\.?|sqft|sf\b|square\s{1,2}(?:feet|foot|ft)|ft2|ft²|pies\s{1,2}cuadrados)",
    _FLAGS,
)
MAX_BEDS = 10
MAX_BATHS = 10
MIN_SQFT = 200
MAX_SQFT = 20_000


def _beds(text: str) -> float | None:
    found = extract_beds(text)
    if found is not None:
        return float(found)
    match = _BEDS_ES.search(text)
    if match and int(match.group(1)) <= MAX_BEDS:
        return float(match.group(1))
    return None


def _baths(text: str) -> float | None:
    match = _BATHS.search(text)
    if match and float(match.group(1)) <= MAX_BATHS:
        return float(match.group(1))
    return None


def _sqft(text: str) -> float | None:
    for match in _SQFT.finditer(text):
        size = int(match.group(1).replace(",", ""))
        if MIN_SQFT <= size <= MAX_SQFT:
            return float(size)
    return None


def extract_claims(text: str) -> AdClaims:
    """Every claim the ad makes, once each, in vocabulary order."""
    text = normalise(text)
    claims = [AdClaim(kind=rule.kind) for rule in _RULES if rule.found(text)]
    for kind, read in (
        (ClaimKind.BEDS, _beds),
        (ClaimKind.BATHS, _baths),
        (ClaimKind.SQFT, _sqft),
    ):
        number = read(text)
        if number is not None:
            claims.append(AdClaim(kind=kind, value=number))
    return AdClaims(claims=claims)

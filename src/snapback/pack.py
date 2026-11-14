"""The tour-prep pack, "Be your own realtor": what the record says, what to ask, and what to do
before paying, for one home. English and Spanish.

Everything here is written by code from fixed text. No model writes a word, and a model is never
asked to choose a line. Three parts:

- "What the record says": one line per fact family, only when the record holds it. A missing
  field is simply absent (no "not on record" lines). Lines from CoStar's research carry
  "as of CoStar's last research"; every line names its source layer.
- "Questions to ask": fixed realtor questions, picked by code from what is missing or
  mismatched, in a fixed priority, at most `MAX_QUESTIONS`.
- "Before you pay": three fixed steps.

Never in a pack: a person's name (a private owner is "a private owner"), a phone number, a
number we do not hold (we hold no fee data), the words "available now", or any word about a
neighbourhood, a school or the people who live nearby (fair housing). `tests/test_pack.py`
holds each of these to the text of both languages.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from snapback.contracts import (
    AS_OF,
    DataSource,
    LicenseResult,
    LicenseStatus,
    OwnerKind,
    OwnerResult,
    PlaceMatch,
    PropertyRecord,
)

LANGS = ("en", "es")
MAX_FACTS = 6
MAX_QUESTIONS = 5
MAX_ROOMS = 4

AS_OF_TEXT = {"en": AS_OF, "es": "según la última investigación de CoStar"}

SRC_COSTAR = {"en": "CoStar record", "es": "Registro de CoStar"}
SRC_MATTERPORT = {"en": "Matterport", "es": "Matterport"}
SRC_VEXCEL = {"en": "Vexcel", "es": "Vexcel"}
SRC_COUNTY = {"en": "County record", "es": "Registro del condado"}
SRC_TREC = {"en": "Texas licence check", "es": "Verificación de licencia de Texas"}

_MONTHS = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
}

T: dict[str, dict[str, str]] = {
    "en": {
        "title": "Tour prep",
        "subtitle": "Be your own realtor: what the record says, what to ask, what to do first.",
        "h.record": "What the record says",
        "h.ask": "Questions to ask",
        "h.pay": "Before you pay",
        "note": "Written by code from records. It says nothing about any person.",
        "home.apt": "{plan}{built}{floors}",
        "home.house": "House, {lead}{built}",
        "built": ", built {year}",
        "floors": ", {n} floors",
        "bed": "{n} bed",
        "bath": "{n} bath",
        "studio": "studio",
        "price.range": "{lo} to {hi} a month",
        "price.one": "{lo} a month",
        "price.units": "{n} unit{s} reported available",
        "price.none": "No units reported available",
        "price.movein": "Listed for move-in from {date}",
        "walkup.yes": "walk-up building",
        "walkup.no": "not a walk-up",
        "elevator": "elevator on record",
        "meter.individual": "individual utility meters",
        "meter.master": "one shared (master) utility meter",
        "parking.ratio": "{r} parking spaces per unit",
        "parking.spaces": "{n} parking space{s}",
        "pets.yes": "pets allowed",
        "pets.no": "pets not allowed",
        "building": "Building: {parts}",
        "owner.company": "Owner of record: {company}",
        "owner.unknown_company": "Owner of record: a company owner",
        "owner.person": "Owner of record: a private owner",
        "scan.apt": "A 3D scan of this building exists",
        "scan.house": "A 3D scan of this home exists",
        "rooms": "rooms labelled in the scan: {rooms}",
        "aerial": "aerial photo captured {date}",
        "licence.ok": "The licence the ad names is an active Texas licence",
        "licence.no": "The licence number in the ad is not an active Texas licence",
        "q.licence": "Ask the agent for their Texas real estate licence number, then look it up "
        "yourself at trec.texas.gov.",
        "q.landlord.company": "Check that the landlord named on the lease is {company}, "
        "the owner of record.",
        "q.landlord.unknown_company": "Check that the landlord named on the lease matches "
        "the owner of record, which is a company.",
        "q.landlord.person": "Check that the landlord named on the lease matches the owner "
        "of record, a private owner.",
        "q.pay": "Ask exactly who you pay and through which official channel, and get it "
        "in writing.",
        "q.fees": "Ask for the total move-in cost and the application fee in writing. "
        "We hold no fee data for this home.",
        "q.tour": "At the tour, check the water pressure, the AC and the appliances, and that "
        "the unit number matches the lease.",
        "q.confirm.office": "Confirm availability with {office}, using a phone number or "
        "website you look up yourself.",
        "q.confirm": "Confirm availability with the leasing office, using a phone number or "
        "website you look up yourself.",
        "pay.1": "Pay nothing before you have toured the home in person and read the lease.",
        "pay.2": "Pay only through the channel written on the lease or on the office's own "
        "website. Never pay cash, Zelle or gift cards to a person.",
        "pay.3": "If the payment details change at the last minute, stop and call the office "
        "on a number you looked up yourself.",
    },
    "es": {
        "title": "Prepara tu visita",
        "subtitle": "Sé tu propio agente: lo que dice el registro, qué preguntar y qué hacer "
        "antes.",
        "h.record": "Lo que dice el registro",
        "h.ask": "Preguntas para hacer",
        "h.pay": "Antes de pagar",
        "note": "Escrito por código a partir de registros. No dice nada sobre ninguna persona.",
        "home.apt": "{plan}{built}{floors}",
        "home.house": "Casa, {lead}{built}",
        "built": ", construido en {year}",
        "floors": ", {n} pisos",
        "bed": "{n} recámara{s}",
        "bath": "{n} baño{s}",
        "studio": "estudio",
        "price.range": "{lo} a {hi} al mes",
        "price.one": "{lo} al mes",
        "price.units": "{n} unidad{es} reportada{s} como disponible{s}",
        "price.none": "Ninguna unidad reportada como disponible",
        "price.movein": "Publicada para mudanza desde el {date}",
        "walkup.yes": "edificio sin elevador (escaleras)",
        "walkup.no": "no es un edificio de escaleras",
        "elevator": "elevador en el registro",
        "meter.individual": "medidores de servicios individuales",
        "meter.master": "un solo medidor de servicios compartido",
        "parking.ratio": "{r} lugares de estacionamiento por unidad",
        "parking.spaces": "{n} lugar{es} de estacionamiento",
        "pets.yes": "se permiten mascotas",
        "pets.no": "no se permiten mascotas",
        "building": "Edificio: {parts}",
        "owner.company": "Dueño en el registro: {company}",
        "owner.unknown_company": "Dueño en el registro: una empresa",
        "owner.person": "Dueño en el registro: un propietario particular",
        "scan.apt": "Existe un escaneo 3D de este edificio",
        "scan.house": "Existe un escaneo 3D de esta casa",
        "rooms": "cuartos etiquetados en el escaneo: {rooms}",
        "aerial": "foto aérea tomada el {date}",
        "licence.ok": "La licencia que menciona el anuncio es una licencia activa de Texas",
        "licence.no": "El número de licencia del anuncio no es una licencia activa de Texas",
        "q.licence": "Pide al agente su número de licencia de bienes raíces de Texas y búscalo "
        "tú mismo en trec.texas.gov.",
        "q.landlord.company": "Confirma que el arrendador que aparece en el contrato es "
        "{company}, el dueño en el registro.",
        "q.landlord.unknown_company": "Confirma que el arrendador que aparece en el contrato "
        "coincide con el dueño en el registro, que es una empresa.",
        "q.landlord.person": "Confirma que el arrendador que aparece en el contrato coincide "
        "con el dueño en el registro, un propietario particular.",
        "q.pay": "Pregunta exactamente a quién pagas y por qué canal oficial, y pídelo por "
        "escrito.",
        "q.fees": "Pide por escrito el costo total de mudanza y la cuota de solicitud. "
        "No tenemos datos de cuotas de esta vivienda.",
        "q.tour": "En la visita, revisa la presión del agua, el aire acondicionado y los "
        "aparatos, y que el número de unidad coincida con el contrato.",
        "q.confirm.office": "Confirma la disponibilidad con {office}, usando un teléfono o un "
        "sitio web que busques tú mismo.",
        "q.confirm": "Confirma la disponibilidad con la oficina de arrendamiento, usando un "
        "teléfono o un sitio web que busques tú mismo.",
        "pay.1": "No pagues nada antes de visitar la vivienda en persona y leer el contrato.",
        "pay.2": "Paga solo por el canal escrito en el contrato o en el sitio web de la "
        "oficina. Nunca pagues en efectivo, por Zelle ni con tarjetas de regalo a una persona.",
        "pay.3": "Si los datos de pago cambian a último momento, detente y llama a la oficina "
        "a un número que hayas buscado tú mismo.",
    },
}


class PackLine(BaseModel):
    key: str
    text: str
    sources: list[str] = Field(default_factory=list)  # the layers this line came from
    as_of: str | None = None  # "as of CoStar's last research", on lines from CoStar's research


class TourPrepPack(BaseModel):
    source: DataSource
    lang: str
    title: str
    subtitle: str
    note: str
    as_of: str
    facts_heading: str
    questions_heading: str
    pay_heading: str
    facts: list[PackLine]
    questions: list[PackLine]
    before_you_pay: list[str]


def _t(lang: str, key: str, **values: Any) -> str:
    return T[lang][key].format(**values)


def _money(n: int) -> str:
    return f"${n:,}"


def _date(lang: str, d: date) -> str:
    month = _MONTHS[lang][d.month - 1]
    return f"{month} {d.day}, {d.year}" if lang == "en" else f"{d.day} {month} {d.year}"


def _plural(lang: str, n: float, key: str, **extra: Any) -> str:
    one = n == 1
    s = "" if one else "s"
    es = "" if one else "es"
    return _t(lang, key, n=n, s=s, es=es, **extra)


def _beds(lang: str, beds: int | None) -> str | None:
    if beds is None:
        return None
    return _t(lang, "studio") if beds == 0 else _plural(lang, beds, "bed")


def _baths(lang: str, baths: float | None) -> str | None:
    if baths is None:
        return None
    n = int(baths) if baths == int(baths) else baths
    return _plural(lang, n, "bath")


def _join(parts: Iterable[str | None]) -> str:
    return ", ".join(p for p in parts if p)


# --- what the record says ---------------------------------------------------------------------


def _home_line(lang: str, place: PlaceMatch | None, record: PropertyRecord | None) -> str | None:
    year = record.year_built if record else None
    floors = record.floors if record else None
    built = _t(lang, "built", year=year) if year else ""
    if place is not None and place.kind == "house":
        beds = _beds(lang, place.beds)
        baths = _baths(lang, place.baths)
        if beds is None and baths is None and not year:
            return None
        return _t(lang, "home.house", lead=_join([beds, baths]), built=built).replace(", ,", ",")
    plan = place.floor_plan if place is not None else None
    stories = _t(lang, "floors", n=floors) if floors else ""
    if not plan and not year and not floors:
        return None
    text = _t(lang, "home.apt", plan=plan or "", built=built, floors=stories)
    return text.lstrip(", ")


def _price_line(lang: str, raw: Any, place: PlaceMatch | None) -> str | None:
    """Price band and units/move-in, only from numbers the record holds."""
    parts: list[str] = []
    lo, hi = (raw.rent_min, raw.rent_max) if raw is not None else (None, None)
    if lo is not None and hi is not None:
        lo, hi = min(lo, hi), max(lo, hi)
        parts.append(
            _t(lang, "price.one", lo=_money(lo))
            if lo == hi
            else _t(lang, "price.range", lo=_money(lo), hi=_money(hi))
        )
    if raw is not None and raw.kind == "house":
        if raw.available_on is not None:
            parts.append(_t(lang, "price.movein", date=_date(lang, raw.available_on)))
    elif raw is not None and raw.units_available is not None:
        n = raw.units_available
        parts.append(_t(lang, "price.none") if n == 0 else _plural(lang, n, "price.units"))
    if not parts:
        return None
    return f"{'; '.join(parts)} {AS_OF_TEXT[lang]}"


def _building_line(lang: str, raw: Any, record: PropertyRecord | None) -> str | None:
    walkup = raw.is_walkup if raw is not None else (record.is_walkup if record else None)
    elevator = raw.has_elevator if raw is not None else (record.has_elevator if record else None)
    metering = raw.metering if raw is not None else (record.metering if record else None)
    ratio = raw.parking_ratio if raw is not None else (record.parking_ratio if record else None)
    spaces = raw.parking_spaces if raw is not None else None
    pets = raw.pets_ok if raw is not None else None
    parts: list[str] = []
    if walkup is True:
        parts.append(_t(lang, "walkup.yes"))
    elif walkup is False:
        parts.append(_t(lang, "walkup.no"))
    if elevator is True:  # only True is shown: an empty list is "not on record"
        parts.append(_t(lang, "elevator"))
    if metering in ("individual", "master"):
        parts.append(_t(lang, f"meter.{metering}"))
    if ratio is not None:
        parts.append(_t(lang, "parking.ratio", r=f"{ratio:g}"))
    if spaces is not None:
        parts.append(_plural(lang, spaces, "parking.spaces"))
    if pets is True:
        parts.append(_t(lang, "pets.yes"))
    elif pets is False:
        parts.append(_t(lang, "pets.no"))
    return _t(lang, "building", parts="; ".join(parts)) if parts else None


def _owner_line(lang: str, owner: OwnerResult | None) -> str | None:
    if owner is None:
        return None
    if owner.kind is OwnerKind.PERSON:
        return _t(lang, "owner.person")
    if owner.company_known and owner.company:
        return _t(lang, "owner.company", company=owner.company)
    return _t(lang, "owner.unknown_company")


def _licence_line(lang: str, licence: LicenseResult | None) -> str | None:
    if licence is None or licence.status is LicenseStatus.NOT_CHECKED:
        return None
    return _t(lang, "licence.ok" if licence.status is LicenseStatus.LICENSED else "licence.no")


def _facts(
    lang: str,
    *,
    raw: Any,
    place: PlaceMatch | None,
    record: PropertyRecord | None,
    owner: OwnerResult | None,
    licence: LicenseResult | None,
    has_scan: bool,
    is_house: bool,
    rooms: list[str],
    aerial_on: date | None,
) -> list[PackLine]:
    out: list[PackLine] = []
    costar = [SRC_COSTAR[lang]]
    as_of = AS_OF_TEXT[lang]

    home = _home_line(lang, place, record)
    if home:
        out.append(PackLine(key="home", text=home, sources=costar, as_of=as_of))
    price = _price_line(lang, raw, place)
    if price:
        out.append(PackLine(key="price", text=price, sources=costar, as_of=as_of))
    building = _building_line(lang, raw, record)
    if building:
        out.append(PackLine(key="building", text=building, sources=costar, as_of=as_of))
    owner_text = _owner_line(lang, owner)
    if owner_text:
        out.append(PackLine(key="owner", text=owner_text, sources=[SRC_COUNTY[lang]]))

    imagery: list[str] = []
    layers: list[str] = []
    if has_scan:
        imagery.append(_t(lang, "scan.house" if is_house else "scan.apt"))
        layers.append(SRC_MATTERPORT[lang])
        if rooms:
            imagery[-1] += "; " + _t(lang, "rooms", rooms=", ".join(rooms[:MAX_ROOMS]))
    if aerial_on is not None:
        label = _t(lang, "aerial", date=_date(lang, aerial_on))
        imagery.append(label if imagery else label[:1].upper() + label[1:])
        layers.append(SRC_VEXCEL[lang])
    if imagery:
        out.append(PackLine(key="imagery", text="; ".join(imagery), sources=layers))

    licence_text = _licence_line(lang, licence)
    if licence_text:
        out.append(PackLine(key="licence", text=licence_text, sources=[SRC_TREC[lang]]))
    return out[:MAX_FACTS]


# --- questions: fixed text, chosen by code ----------------------------------------------------


def _questions(
    lang: str,
    *,
    owner: OwnerResult | None,
    licence: LicenseResult | None,
    office: str | None,
    units_reported: bool,
) -> list[PackLine]:
    """Priority order; a question that the record already settles, or cannot apply to, is left
    out: the licence question when the licence is active, the landlord check only when an
    owner of record is held, the availability check only with an office or a reported count."""
    out: list[PackLine] = []

    def add(key: str, text_key: str, **values: Any) -> None:
        out.append(PackLine(key=key, text=_t(lang, text_key, **values)))

    if licence is None or licence.status is not LicenseStatus.LICENSED:
        add("licence", "q.licence")
    if owner is not None:
        if owner.kind is OwnerKind.PERSON:
            add("landlord", "q.landlord.person")
        elif owner.company_known and owner.company:
            add("landlord", "q.landlord.company", company=owner.company)
        else:
            add("landlord", "q.landlord.unknown_company")
    add("pay", "q.pay")
    add("fees", "q.fees")
    add("tour", "q.tour")
    if office:
        add("confirm", "q.confirm.office", office=office)
    elif units_reported:
        add("confirm", "q.confirm")
    return out[:MAX_QUESTIONS]


# --- the pack ---------------------------------------------------------------------------------


def build_tour_prep(
    *,
    source: DataSource,
    lang: str = "en",
    place: PlaceMatch | None = None,
    raw: Any = None,
    record: PropertyRecord | None = None,
    owner: OwnerResult | None = None,
    licence: LicenseResult | None = None,
    room_labels: Iterable[str] = (),
    aerial_on: date | None = None,
) -> TourPrepPack:
    """One pack, from the layers we hold. Every input is optional: a missing one leaves its line
    out and never adds a "not on record" line. `raw` is the place's record facts
    (`search.place_and_raw_for`); a checked ad passes `record`, `owner`, `licence` and rooms."""
    lang = lang if lang in LANGS else "en"
    is_house = (
        (place.kind == "house")
        if place is not None
        else bool(record is not None and record.property_type == "house")
    )
    has_scan = bool(place.has_3d_scan) if place is not None else bool(record and record.model_ids)
    rooms = sorted({r.strip() for r in room_labels if r and r.strip()})
    office = (place.office_on_record or "").strip() if place is not None else ""
    if not office and record is not None:
        office = (record.manager_company or "").strip()
    units_reported = raw is not None and getattr(raw, "units_available", None) is not None

    facts = _facts(
        lang,
        raw=raw,
        place=place,
        record=record,
        owner=owner,
        licence=licence,
        has_scan=has_scan,
        is_house=is_house,
        rooms=rooms,
        aerial_on=aerial_on,
    )
    questions = _questions(
        lang, owner=owner, licence=licence, office=office or None, units_reported=units_reported
    )
    return TourPrepPack(
        source=source,
        lang=lang,
        title=_t(lang, "title"),
        subtitle=_t(lang, "subtitle"),
        note=_t(lang, "note"),
        as_of=AS_OF_TEXT[lang],
        facts_heading=_t(lang, "h.record"),
        questions_heading=_t(lang, "h.ask"),
        pay_heading=_t(lang, "h.pay"),
        facts=facts,
        questions=questions,
        before_you_pay=[_t(lang, "pay.1"), _t(lang, "pay.2"), _t(lang, "pay.3")],
    )

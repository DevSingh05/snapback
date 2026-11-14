"""The tour-prep pack (be your own realtor): lines from the record only, questions chosen by code,
EN and ES in step, none of the words or digits a pack must never carry."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import (
    DataSource,
    LicenseResult,
    LicenseStatus,
    OwnerKind,
    OwnerResult,
)
from snapback.pack import LANGS, MAX_FACTS, MAX_QUESTIONS, SRC_TREC, T, build_tour_prep
from snapback.search import place_and_raw_for
from snapback.settings import Settings

PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")
FORBIDDEN = (
    "available now",
    "scam",
    "fraud",
    "safe",
    "verified",
    "legit",
    "neighborhood",
    "neighbourhood",
    "school",
    "crime",
    "vecindario",
    "escuela",
    "colonia",
    "barrio",
    "family",
    "familia",
    "tenant",
    "inquilino",
    "vecinos",
    "neighbors",
)
LOOKUPS = KitLookups(DataSource.FIXTURE)
STUDIO = ("fx-prop-3", "studio / 1 bath|1400|1600|3")
HOUSE = ("880001", "house")
BARE = ("fx-prop-4", "1 bed / 1 bath|1200|1400|None")


def pack_of(target, lang="en", **extra):
    place, raw = place_and_raw_for(target[0], None, LOOKUPS, None, target[1])
    return build_tour_prep(
        source=place.source,
        lang=lang,
        place=place,
        raw=raw,
        record=LOOKUPS.record(target[0]),
        **extra,
    )


def all_text(pack) -> str:
    lines = [f.text for f in pack.facts] + [q.text for q in pack.questions]
    return "\n".join(lines + pack.before_you_pay + [pack.title, pack.subtitle, pack.note])


def keys(lines) -> list[str]:
    return [line.key for line in lines]


def test_facts_come_only_from_fields_the_record_holds():
    full = pack_of(STUDIO, aerial_on=date(2025, 6, 1))
    text = " ".join(f.text for f in full.facts)
    assert "built 1998" in text and "12 floors" in text and "$1,400 to $1,600" in text
    assert "3 units reported available" in text and "elevator on record" in text
    assert "individual utility meters" in text and "not a walk-up" in text
    bare = pack_of(BARE)  # no scan, no units count, no elevator, no parking on this plan
    bare_text = " ".join(f.text for f in bare.facts)
    assert "elevator" not in bare_text and "3D scan" not in bare_text
    assert "units" not in bare_text and "parking" not in bare_text
    assert "not on record" not in all_text(bare).lower()
    assert "imagery" not in keys(bare.facts)  # no scan and no aerial date: no line at all


def test_a_missing_field_leaves_no_line_and_no_spam():
    empty = build_tour_prep(source=DataSource.FIXTURE)
    assert empty.facts == []
    assert "not on record" not in all_text(empty).lower()
    assert keys(empty.questions) == ["licence", "pay", "fees", "tour"]


def test_costar_lines_carry_the_as_of_label_and_every_line_names_its_source():
    pack = pack_of(STUDIO, aerial_on=date(2025, 6, 1))
    for line in pack.facts:
        assert line.sources
        if line.sources == ["CoStar record"]:
            assert line.as_of == "as of CoStar's last research"
    price = next(f for f in pack.facts if f.key == "price")
    assert price.text.endswith("as of CoStar's last research")
    imagery = next(f for f in pack.facts if f.key == "imagery")
    assert imagery.sources == ["Matterport", "Vexcel"] and "Jun 1, 2025" in imagery.text


def test_house_pack_uses_house_wording_and_move_in_date():
    pack = pack_of(HOUSE)
    text = " ".join(f.text for f in pack.facts)
    assert text.startswith("House, 3 bed, 2 bath")
    assert "Listed for move-in from Dec 1, 2026" in text and "2 parking spaces" in text
    assert "this home exists" in text


def test_room_labels_from_the_scan_are_listed_once():
    pack = pack_of(STUDIO, room_labels=["Kitchen", "Bedroom", "Kitchen", ""])
    imagery = next(f for f in pack.facts if f.key == "imagery")
    assert "rooms labelled in the scan: Bedroom, Kitchen" in imagery.text


def test_owner_line_names_a_company_only_when_known_never_a_person():
    known = OwnerResult(kind=OwnerKind.COMPANY, company="Oak Rentals LLC", company_known=True)
    unknown = OwnerResult(
        kind=OwnerKind.COMPANY, company="Some Holdings Trust", company_known=False
    )
    person = OwnerResult(kind=OwnerKind.PERSON, company=None)
    text = lambda o: " ".join(f.text for f in pack_of(STUDIO, owner=o).facts)  # noqa: E731
    assert "Owner of record: Oak Rentals LLC" in text(known)
    assert "Owner of record: a company owner" in text(unknown)
    assert "Some Holdings" not in text(unknown) and "Some Holdings" not in all_text(
        pack_of(STUDIO, owner=unknown)
    )
    assert "Owner of record: a private owner" in text(person)


def test_questions_are_chosen_by_code_from_the_gaps():
    plain = pack_of(STUDIO)
    assert "landlord" not in keys(plain.questions)  # no owner of record held: nothing to match
    owner = OwnerResult(kind=OwnerKind.COMPANY, company="Oak Rentals LLC", company_known=True)
    with_owner = pack_of(STUDIO, owner=owner)
    landlord = next(q for q in with_owner.questions if q.key == "landlord")
    assert "Oak Rentals LLC" in landlord.text and "owner of record" in landlord.text
    licensed = LicenseResult(status=LicenseStatus.LICENSED)
    assert "licence" not in keys(pack_of(STUDIO, licence=licensed).questions)
    assert "licence" in keys(
        pack_of(STUDIO, licence=LicenseResult(status=LicenseStatus.NOT_FOUND)).questions
    )
    assert "licence" in keys(plain.questions)
    assert len(with_owner.questions) <= MAX_QUESTIONS and len(plain.facts) <= MAX_FACTS
    # priority is fixed: licence, landlord, pay, fees, tour, confirm
    assert keys(with_owner.questions) == ["licence", "landlord", "pay", "fees", "tour"]


def test_confirm_question_needs_an_office_or_a_reported_count():
    bare = build_tour_prep(source=DataSource.FIXTURE)
    assert "confirm" not in keys(bare.questions)
    house = build_tour_prep(source=DataSource.FIXTURE, record=None)
    assert "confirm" not in keys(house.questions)
    assert "confirm" in keys(pack_of(STUDIO).questions)


def test_licence_status_line_only_when_checked():
    ok = pack_of(STUDIO, licence=LicenseResult(status=LicenseStatus.LICENSED))
    assert "active Texas license" in " ".join(f.text for f in ok.facts)
    nc = pack_of(STUDIO, licence=LicenseResult(status=LicenseStatus.NOT_CHECKED))
    assert "licence" not in keys(nc.facts)


RENTER_PHRASE = {"en": "the license number you gave", "es": "el número de licencia que diste"}


@pytest.mark.parametrize("lang", LANGS)
def test_a_renter_typed_number_never_reads_as_a_fact_about_the_ad(lang):
    for status in (LicenseStatus.LICENSED, LicenseStatus.NOT_FOUND):
        renter = LicenseResult(status=status, number_from="renter")
        ad = LicenseResult(status=status, number_from="ad")
        line = next(f for f in pack_of(STUDIO, lang, licence=renter).facts if f.key == "licence")
        ad_line = next(f for f in pack_of(STUDIO, lang, licence=ad).facts if f.key == "licence")
        assert RENTER_PHRASE[lang] in line.text.lower()
        assert RENTER_PHRASE[lang] not in ad_line.text.lower()
        assert line.text != ad_line.text
    # NOT_CHECKED says nothing, whoever typed the number
    nc = LicenseResult(status=LicenseStatus.NOT_CHECKED, number_from="renter")
    assert "licence" not in keys(pack_of(STUDIO, lang, licence=nc).facts)


def test_english_table_spells_license_the_american_way():
    for key, text in T["en"].items():
        assert "licence" not in text.lower(), key
    assert "licence" not in SRC_TREC["en"].lower()


def test_home_line_starts_with_a_capital_and_pluralises_floors():
    one = LOOKUPS.record("fx-prop-3").model_copy(update={"floors": 1})
    two = LOOKUPS.record("fx-prop-3").model_copy(update={"floors": 2})
    for lang, floors in (("en", ("1 floor", "2 floors")), ("es", ("1 piso", "2 pisos"))):
        place, raw = place_and_raw_for(STUDIO[0], None, LOOKUPS, None, STUDIO[1])
        for record, expect in ((one, floors[0]), (two, floors[1])):
            pack = build_tour_prep(
                source=place.source, lang=lang, place=place, raw=raw, record=record
            )
            home = next(f for f in pack.facts if f.key == "home").text
            assert expect in home and f"1 {floors[0].split()[1]}s" not in home
            assert home[0].isupper(), home
    # no plan on record: the line must still start with a capital
    pack = build_tour_prep(source=DataSource.FIXTURE, record=two)
    assert next(f for f in pack.facts if f.key == "home").text[0].isupper()


def test_case_route_lists_only_rooms_photographed_in_the_claimed_building(client):
    from snapback.contracts import LocateResult, LocateStatus, PhotoLocation

    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month, pets ok"}).json()
    case = client.app.state.store.get(made["case_id"])
    photos = [
        PhotoLocation(photo_id="a", status=LocateStatus.LOCATED_IN_CLAIMED, room_label="Kitchen"),
        PhotoLocation(photo_id="b", status=LocateStatus.LOCATED_ELSEWHERE, room_label="Garage"),
        PhotoLocation(photo_id="c", status=LocateStatus.NOT_LOCATED, room_label="Pool"),
    ]
    case.property_id = "fx-prop-3"  # a building with a scan, so the rooms line can show
    case.evidence.locate = LocateResult(
        case_id=made["case_id"], photos=photos, thresholds_version="t"
    )
    url = f"/cases/{made['case_id']}/tour-prep"
    body = client.get(url, headers={"Authorization": f"Bearer {made['read_token']}"}).json()
    text = " ".join(f["text"] for f in body["facts"])
    assert "Kitchen" in text and "Garage" not in text and "Pool" not in text


def test_three_fixed_steps_before_paying():
    for lang in LANGS:
        assert len(pack_of(STUDIO, lang).before_you_pay) == 3


def test_en_and_es_tables_have_the_same_keys_and_placeholders():
    assert set(T["en"]) == set(T["es"])
    field = re.compile(r"\{(\w+)\}")
    for key in T["en"]:
        if key in ("price.units", "parking.spaces", "bed", "bath"):
            continue  # plural suffix placeholders differ by language
        assert set(field.findall(T["en"][key])) == set(field.findall(T["es"][key])), key


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("target", [STUDIO, HOUSE, BARE])
def test_forbidden_words_digits_and_dashes_never_appear(lang, target):
    owner = OwnerResult(kind=OwnerKind.COMPANY, company="Oak Rentals LLC", company_known=True)
    text = all_text(pack_of(target, lang, owner=owner, aerial_on=date(2025, 6, 1)))
    lowered = text.lower()
    for word in FORBIDDEN:
        assert word not in lowered, word
    assert not PHONE.search(text)
    assert "—" not in text and "–" not in text


def test_spanish_pack_is_spanish_and_same_shape():
    en, es = pack_of(STUDIO, "en"), pack_of(STUDIO, "es")
    assert keys(en.facts) == keys(es.facts) and keys(en.questions) == keys(es.questions)
    assert es.title == "Prepara tu visita" and es.as_of == "según la última investigación de CoStar"
    assert "unidades reportadas como disponibles" in " ".join(f.text for f in es.facts)
    assert es.facts[0].as_of == es.as_of


def test_unknown_language_falls_back_to_english():
    assert build_tour_prep(source=DataSource.FIXTURE, lang="fr").lang == "en"


# --- API ---------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=LOOKUPS))


def test_place_route_is_public_labelled_and_bilingual(client):
    url = "/places/fx-prop-3/tour-prep"
    body = client.get(url, params={"plan_key": STUDIO[1]}).json()
    assert body["source"] == "fixture" and body["lang"] == "en"
    assert body["as_of"] == "as of CoStar's last research"
    assert [f["key"] for f in body["facts"]][0] == "home"
    es = client.get(url, params={"plan_key": STUDIO[1], "lang": "es"}).json()
    assert es["lang"] == "es" and es["title"] == "Prepara tu visita"
    assert "owner" not in [f["key"] for f in body["facts"]]  # public: no county owner data
    assert "licence" not in [f["key"] for f in body["facts"]]


def test_place_route_errors(client):
    assert client.get("/places/nope/tour-prep").status_code == 404
    assert client.get("/places/fx-prop-3/tour-prep").status_code == 422  # several plans, no key
    assert client.get("/places/880001/tour-prep").status_code == 200  # a unique plan needs no key
    assert client.get("/places/fx-prop-3/tour-prep?lang=fr&plan_key=x").status_code == 422


def test_case_route_needs_the_read_token_in_a_header(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month, pets ok"}).json()
    url = f"/cases/{made['case_id']}/tour-prep"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get(f"{url}?token={made['read_token']}").status_code == 401
    ok = client.get(url, headers={"Authorization": f"Bearer {made['read_token']}"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["source"] == "fixture"
    assert [q["key"] for q in body["questions"]][:1] == ["licence"]
    assert len(body["before_you_pay"]) == 3
    es = client.get(
        url + "?lang=es", headers={"Authorization": f"Bearer {made['read_token']}"}
    ).json()
    assert es["lang"] == "es"


def test_known_capture_date_never_fetches(tmp_path):
    from snapback.adapters.vexcel import known_capture_date

    record = LOOKUPS.record("fx-prop-3")
    assert known_capture_date(record, source=DataSource.FIXTURE) == date(2025, 6, 1)
    # live with nothing cached: not known, and no network is touched
    assert known_capture_date(record, source=DataSource.LIVE, data_dir=tmp_path) is None

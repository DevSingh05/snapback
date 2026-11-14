"""Ad vs record, step 1: the fixed vocabulary of checkable claims, in English and Spanish.

Conservative on purpose: a claim is found only when the ad says it in a plain way, and a
denied claim ("no carpet", "not pet friendly") is never read as a claim.
"""

import pytest

from snapback.agent.intake.claims import ClaimKind, extract_claims

K = ClaimKind


def kinds(text: str) -> set[ClaimKind]:
    return {claim.kind for claim in extract_claims(text).claims}


def value(text: str, kind: ClaimKind) -> float | None:
    return next(c.value for c in extract_claims(text).claims if c.kind is kind)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Beautiful hardwood floors throughout", K.FLOOR_WOOD),
        ("wood flooring in the living room", K.FLOOR_WOOD),
        ("Engineered wood and fresh paint", K.FLOOR_WOOD),
        ("Carpeted bedrooms", K.FLOOR_CARPET),
        ("new carpet", K.FLOOR_CARPET),
        ("Ceramic tile floors in the kitchen", K.FLOOR_TILE),
        ("tile throughout the home", K.FLOOR_TILE),
        ("Laminate flooring", K.FLOOR_LAMINATE),
        ("luxury vinyl plank in every room", K.FLOOR_LAMINATE),
        ("Washer and dryer included", K.WASHER_DRYER),
        ("in-unit laundry", K.WASHER_DRYER),
        ("W/D in unit", K.WASHER_DRYER),
        ("Private pool and spa", K.POOL),
        ("two car garage", K.GARAGE),
        ("Covered carport for one car", K.GARAGE),
        ("Driveway parking for two cars", K.GARAGE),
        ("Fenced backyard", K.YARD),
        ("large yard", K.YARD),
        ("Pet friendly", K.PETS),
        ("pets allowed with deposit", K.PETS),
        ("Cats and dogs welcome", K.PETS),
    ],
)
def test_english_claims(text, kind):
    assert kind in kinds(text)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Pisos de madera en toda la casa", K.FLOOR_WOOD),
        ("recámaras con alfombra", K.FLOOR_CARPET),
        ("pisos de azulejo", K.FLOOR_TILE),
        ("piso laminado", K.FLOOR_LAMINATE),
        ("Incluye lavadora y secadora", K.WASHER_DRYER),
        ("Con piscina privada", K.POOL),
        ("Cochera para dos carros", K.GARAGE),
        ("Patio trasero con cerca", K.YARD),
        ("Se aceptan mascotas", K.PETS),
        ("mascotas permitidas", K.PETS),
        ("Bajo nueva administración", K.NEW_MANAGEMENT),
        ("Casa recién vendida", K.JUST_SOLD),
        ("El dueño está fuera del país", K.OWNER_AWAY),
        ("No puedo mostrar la casa", K.CANT_SHOW),
    ],
)
def test_spanish_claims(text, kind):
    assert kind in kinds(text)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("No carpet anywhere, all hardwood", K.FLOOR_CARPET),
        ("carpet-free home", K.FLOOR_CARPET),
        ("Without carpet", K.FLOOR_CARPET),
        ("Not pet friendly", K.PETS),
        ("No pets allowed", K.PETS),
        ("Non-pet friendly building", K.PETS),
        ("no pool, no garage", K.POOL),
        ("no pool, no garage", K.GARAGE),
        ("No pool or garage", K.GARAGE),
        ("Washer and dryer not included", K.WASHER_DRYER),
        ("No washer/dryer", K.WASHER_DRYER),
        ("Sin alfombra", K.FLOOR_CARPET),
        ("No se aceptan mascotas", K.PETS),
        ("Sin mascotas", K.PETS),
        ("Sin piscina", K.POOL),
        ("No garage", K.GARAGE),
        ("No carport", K.GARAGE),
    ],
)
def test_a_denied_claim_is_not_a_claim(text, kind):
    assert kind not in kinds(text)


def test_a_comma_ends_the_denial():
    # "no carpet" does not deny the hardwood that comes after a comma.
    assert K.FLOOR_WOOD in kinds("No carpet, hardwood floors")


@pytest.mark.parametrize(
    "text",
    [
        "W/D hookups in the garage",
        "Washer and dryer hookups only",
        "shared laundry room on site",
        "coin laundry downstairs",
    ],
)
def test_hookups_and_shared_laundry_are_not_an_in_unit_washer(text):
    assert K.WASHER_DRYER not in kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "tile backsplash and granite counters",
        "tiled shower",
        "wood fence around the yard",
        "wood-look tile in the kitchen",
        "faux wood blinds",
        "laminate countertops",
        "pool table in the game room",
        "carpool lane access nearby",
        "street parking only",
        "community pool and gym",
        "garage sale this weekend",
    ],
)
def test_words_that_are_not_about_the_home_are_not_claims(text):
    found = kinds(text)
    assert not found & {
        K.FLOOR_WOOD,
        K.FLOOR_TILE,
        K.FLOOR_LAMINATE,
        K.POOL,
        K.GARAGE,
        K.WASHER_DRYER,
    }


def test_numbers_beds_baths_and_square_feet():
    text = "Spacious 3 bedroom, 2.5 bath home, 1,450 sq ft"
    assert value(text, K.BEDS) == 3
    assert value(text, K.BATHS) == 2.5
    assert value(text, K.SQFT) == 1450
    assert value("Studio near everything", K.BEDS) == 0
    assert value("3 recámaras, 2 baños, 1200 pies cuadrados", K.BEDS) == 3
    assert value("3 recámaras, 2 baños, 1200 pies cuadrados", K.BATHS) == 2
    assert value("3 recámaras, 2 baños, 1200 pies cuadrados", K.SQFT) == 1200


def test_a_number_that_counts_something_else_is_not_square_feet():
    assert K.SQFT not in kinds("Rent $1,450 per month, 12 month lease")
    assert K.SQFT not in kinds("2 sq ft")  # too small to be a home


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Now under new management!", K.NEW_MANAGEMENT),
        ("New property management, same great home", K.NEW_MANAGEMENT),
        ("Under new ownership", K.NEW_OWNERSHIP),
        ("The house just sold, so the price is low", K.JUST_SOLD),
        ("recently sold, new owner", K.JUST_SOLD),
        ("Owner is out of town, so no calls", K.OWNER_AWAY),
        ("I'm overseas right now", K.OWNER_AWAY),
        ("Owner is away on business", K.OWNER_AWAY),
        ("I can't show it in person", K.CANT_SHOW),
        ("Unable to show the home until you apply", K.CANT_SHOW),
        ("No showings, apply online", K.CANT_SHOW),
    ],
)
def test_pretext_phrases(text, kind):
    assert kind in kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "Not under new management",
        "We can show it any day",
        "Owner is out of the office until 9",
        "Showings daily 9 to 5",
        "A new manager special: $99 deposit",
    ],
)
def test_ordinary_wording_is_not_a_pretext(text):
    found = kinds(text)
    assert not found & {
        K.NEW_MANAGEMENT,
        K.NEW_OWNERSHIP,
        K.JUST_SOLD,
        K.OWNER_AWAY,
        K.CANT_SHOW,
    }


def test_each_claim_is_found_once_and_the_list_is_bounded():
    found = extract_claims("hardwood floors, hardwood floors, wood flooring " * 50).claims
    assert [c.kind for c in found].count(K.FLOOR_WOOD) == 1


def test_a_long_hostile_text_is_read_in_bounded_time():
    import time

    start = time.perf_counter()
    extract_claims("no " * 20000 + "carpet " * 20000 + "a" * 100000)
    assert time.perf_counter() - start < 1.0


def test_no_claim_in_plain_text():
    assert extract_claims("Nice home near the park, call anytime.").claims == []


def test_a_spaced_dash_ends_the_denial_too():
    assert K.FLOOR_WOOD in kinds("No carpet \u2014 all hardwood")
    assert K.FLOOR_WOOD in kinds("No carpet \u2013 all hardwood")
    assert K.FLOOR_WOOD in kinds("No carpet - all hardwood")

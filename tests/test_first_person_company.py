"""(g') on #10: a poster who names their company in the first person.

"Hi, this is Fixture Living LLC, the property manager" names a company as surely as "managed by
Fixture Living LLC" does, and intake used to miss it, so a different manager in the ad showed
nothing. Only a name that ends in a company word is taken: a person's name never is.

Every name here is made up.
"""

import pytest

from snapback.agent.intake.fields import extract_contacts


@pytest.mark.parametrize(
    "text, company",
    [
        ("Hi, this is Fixture Living LLC, the property manager.", "Fixture Living LLC"),
        (
            "This is Fixture Property Management, we have a 2 bed open.",
            "Fixture Property Management",
        ),
        ("hello this is Oak Court Realty", "Oak Court Realty"),
        ("Hi this is Maria with Fixture Living LLC.", "Fixture Living LLC"),
        ("I'm Sam from Harbor Point Properties, text me.", "Harbor Point Properties"),
        ("I am with Fixture Homes Group and can show it today.", "Fixture Homes Group"),
        ("I'm from Lakeside Rentals.", "Lakeside Rentals"),
        ("We are Fixture Living LLC, the leasing office.", "Fixture Living LLC"),
        ("We're Bayou Residential and we manage this building.", "Bayou Residential"),
        (
            "Writing on behalf of Fixture Property Management LLC.",
            "Fixture Property Management LLC",
        ),
        ("I am the property manager at Fixture Living LLC.", "Fixture Living LLC"),
        ("I'm the leasing agent for Oak Court Apartments.", "Oak Court Apartments"),
        ("Somos Fixture Living LLC, la oficina de alquiler.", "Fixture Living LLC"),
        ("Soy de Harbor Point Properties.", "Harbor Point Properties"),
    ],
)
def test_a_company_named_in_the_first_person_is_heard(text, company):
    assert extract_contacts(text).company == company


@pytest.mark.parametrize(
    "text",
    [
        "Hi, this is John Smith, the owner.",
        "This is Maria. Text me for a tour.",
        "This is a great home near the park.",
        "This is The Best Deal In Town.",
        "We are located two blocks from the station.",
        "We are Open Saturday And Sunday.",
        "I'm from Houston and I own this house.",
        "I am with my family abroad until spring.",
        "I'm the owner. Rent is $1,900.",
        "On behalf of my mother I am renting her house.",
        "I am the property manager.",
        "",
    ],
)
def test_a_person_or_a_plain_sentence_is_not_a_company(text):
    assert extract_contacts(text).company is None


def test_the_plain_wording_still_wins_when_both_are_there():
    text = "Hi, this is Oak Court Realty. Managed by Fixture Living LLC."
    assert extract_contacts(text).company == "Fixture Living LLC"


def test_a_long_run_of_capitalised_words_cannot_stall_it():
    import time

    hostile = "This is " + "Aa " * 20000
    start = time.perf_counter()
    assert extract_contacts(hostile).company is None
    assert time.perf_counter() - start < 0.5

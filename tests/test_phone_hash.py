"""The phone hash lanes A and D share (A7 #67, D7 #66). 555-01xx numbers are fictional."""

from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, phone_hash, phone_salt
from snapback.contracts import DataSource
from snapback.settings import Settings

OFFICE = "(555) 010-0142"


def test_one_number_written_five_ways_gives_one_hash():
    ways = [OFFICE, "555-010-0142", "555.010.0142", "+1 555 010 0142", "15550100142"]
    assert len({phone_hash(number, FIXTURE_PHONE_SALT) for number in ways}) == 1


def test_another_number_or_another_salt_gives_another_hash():
    ours = phone_hash(OFFICE, FIXTURE_PHONE_SALT)
    assert ours != phone_hash("555-010-0177", FIXTURE_PHONE_SALT)
    assert ours != phone_hash(OFFICE, "another-salt")


def test_the_hash_is_not_the_number_and_text_that_is_no_number_has_none():
    ours = phone_hash(OFFICE, FIXTURE_PHONE_SALT)
    assert len(ours) == 64 and "5550100142" not in ours
    assert phone_hash("call me", FIXTURE_PHONE_SALT) is None
    assert phone_hash("555-0142", FIXTURE_PHONE_SALT) is None  # seven digits is not a number
    assert phone_hash("1" * 5000, FIXTURE_PHONE_SALT) is None  # and a wall of digits is not


def test_where_the_salt_comes_from():
    fixture = Settings(_env_file=None)
    assert phone_salt(fixture) == FIXTURE_PHONE_SALT

    configured = Settings(_env_file=None, snapback_phone_salt="set-by-a-human")
    assert phone_salt(configured) == "set-by-a-human"
    assert "set-by-a-human" not in repr(configured)  # a SecretStr: it stays out of logs

    live = Settings(_env_file=None, snapback_data_source=DataSource.LIVE)
    made = phone_salt(live)
    assert made not in (FIXTURE_PHONE_SALT, "") and len(made) >= 32
    assert phone_salt(live) == made  # the same for the life of the process

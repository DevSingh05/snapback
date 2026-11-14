"""The leak helper must ignore timestamps and UUIDs but still catch real leaks."""

from leakcheck import leaked

STAMP = '{"at": "2026-11-14T15:27:52.160025Z", "id": "c3f9a1b2-1600-4d1e-9a77-0123456789ab"}'


def test_timestamps_and_uuids_cannot_match_a_short_needle():
    assert leaked(["1600", "0123", "160025", "52.16"], STAMP) == []


def test_a_value_glued_into_an_identifier_is_still_a_leak():
    assert leaked(["1600"], "rent_band_min_1600") == ["1600"]
    assert leaked(["0142"], "call-555-010-0142") == ["0142"]
    assert leaked(["4B"], "unit_number_4B_floor2") == ["4B"]


def test_a_short_value_in_ordinary_text_is_still_a_leak():
    assert leaked(["1600"], STAMP, "rent was 1600 a month") == ["1600"]


def test_long_needles_are_searched_in_the_raw_text():
    secret = "fixtureliving.example"
    assert leaked([secret, "other-host"], f"visit {secret}") == [secret]
    hashed = "a1b2c3d4e5f60718"
    assert leaked([hashed], f"hash={hashed}") == [hashed]


def test_none_needles_are_skipped():
    assert leaked([None], "anything") == []

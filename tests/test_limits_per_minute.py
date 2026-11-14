"""PerMinuteLimit keeps its memory bounded."""

from snapback.api.limits import PerMinuteLimit


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_allows_the_limit_then_refuses_and_recovers_after_a_minute():
    clock = Clock()
    limit = PerMinuteLimit(2, clock)
    assert [limit.allow("a"), limit.allow("a"), limit.allow("a")] == [True, True, False]
    assert limit.allow("b")
    clock.now += 61
    assert limit.allow("a")


def test_stale_keys_are_dropped_once_many_are_held(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(PerMinuteLimit, "SWEEP_ABOVE", 50)
    limit = PerMinuteLimit(5, clock)
    for n in range(60):
        limit.allow(f"old-{n}")
    clock.now += 61
    limit.allow("fresh")
    assert set(limit._hits) == {"fresh"}


def test_recent_keys_survive_a_sweep_and_the_hard_cap_refuses_new_keys(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(PerMinuteLimit, "SWEEP_ABOVE", 10)
    monkeypatch.setattr(PerMinuteLimit, "MAX_KEYS", 20)
    limit = PerMinuteLimit(5, clock)
    for n in range(20):
        assert limit.allow(f"k{n}")
    assert limit.allow("k0")  # a key already held is still served
    assert limit.allow("new") is False  # full of live keys: refuse rather than grow
    assert len(limit._hits) == 20

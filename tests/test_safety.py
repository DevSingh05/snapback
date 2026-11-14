"""D5: per-renter limits, the delete command and purge."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from snapback.safety import (
    PurgeRefusedError,
    RenterLimits,
    SafetyStore,
    delete_case,
    delete_renter,
    purge,
)


class Day:
    def __init__(self) -> None:
        self.today = date(2026, 11, 14)

    def __call__(self) -> date:
        return self.today


def _memory_db(data: Path) -> Path:
    """Stand-in for V5's memory DB: any table with a case_id column is cleaned."""
    db = data / "memory" / "memory.sqlite"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as con:
        con.execute("create table hashes (case_id text, photo_id text, phash text)")
        con.execute("create table settings (k text, v text)")
        con.executemany(
            "insert into hashes values (?, ?, ?)",
            [("fx-a", "p1", "00ff"), ("fx-a", "p2", "0f0f"), ("fx-b", "p3", "ff00")],
        )
        con.execute("insert into settings values ('ttl_days', '7')")
    con.close()
    return db


def _rows(db: Path, table: str) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(f"select * from {table}").fetchall()  # noqa: S608
    finally:
        con.close()


def test_fourth_check_in_a_day_is_refused(tmp_path):
    day = Day()
    limits = RenterLimits(tmp_path / "data", per_day=3, today=day)
    for _ in range(3):
        assert limits.check_limit("fx-renter")
        limits.count("fx-renter")
    assert not limits.check_limit("fx-renter")
    assert limits.check_limit("fx-other")
    day.today = date(2026, 11, 15)
    assert limits.check_limit("fx-renter")


def test_limits_survive_a_restart(tmp_path):
    day = Day()
    for _ in range(3):
        RenterLimits(tmp_path / "data", per_day=3, today=day).count("fx-renter")
    assert not RenterLimits(tmp_path / "data", per_day=3, today=day).check_limit("fx-renter")


def test_a_check_that_did_not_start_uses_no_allowance(tmp_path):
    limits = RenterLimits(tmp_path / "data", per_day=1, today=Day())
    assert limits.check_limit("fx-renter")  # asking does not count
    assert limits.check_limit("fx-renter")


def test_delete_removes_memory_rows(tmp_path):
    data = tmp_path / "data"
    db = _memory_db(data)
    report = delete_case("fx-a", data)
    assert _rows(db, "hashes") == [("fx-b", "p3", "ff00")]
    assert _rows(db, "settings") == [("ttl_days", "7")]
    assert report.rows == 2


def test_delete_removes_the_case_folder_and_its_photos(tmp_path):
    data = tmp_path / "data"
    photos = data / "cases" / "fx-a"
    photos.mkdir(parents=True)
    (photos / "reply-1.jpg").write_bytes(b"\xff\xd8")
    (data / "cases" / "fx-b").mkdir()
    report = delete_case("fx-a", data)
    assert not photos.exists()
    assert (data / "cases" / "fx-b").exists()
    assert report.files == 1


def test_delete_refuses_a_case_id_that_walks_out_of_the_folder(tmp_path):
    data = tmp_path / "data"
    (data / "cases").mkdir(parents=True)
    keep = tmp_path / "keep.txt"
    keep.write_text("x")
    with pytest.raises(ValueError):
        delete_case("../../keep.txt", data)
    assert keep.exists()


def test_delete_command_removes_every_case_of_that_renter(tmp_path):
    data = tmp_path / "data"
    db = _memory_db(data)
    store = SafetyStore(data)
    store.register_case("fx-a", "fx-renter")
    store.register_case("fx-b", "fx-someone-else")
    deleted = delete_renter("fx-renter", data)
    assert deleted == ["fx-a"]
    assert _rows(db, "hashes") == [("fx-b", "p3", "ff00")]
    assert store.cases_of("fx-renter") == []


def test_purge_empties_data_dir_in_tmp(tmp_path):
    data = tmp_path / "data"
    _memory_db(data)
    (data / "raw" / "costar").mkdir(parents=True)
    (data / "raw" / "costar" / "kit.jsonl").write_text("{}")
    (data / ".gitkeep").write_text("")
    removed = purge(data)
    assert data.is_dir()
    assert [p.name for p in data.iterdir()] == [".gitkeep"]
    assert removed >= 2


def test_purge_refuses_a_folder_not_named_data(tmp_path):
    other = tmp_path / "src"
    other.mkdir()
    (other / "keep.py").write_text("x")
    with pytest.raises(PurgeRefusedError):
        purge(other)
    assert (other / "keep.py").exists()

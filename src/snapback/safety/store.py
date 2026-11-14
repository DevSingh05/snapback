"""A small SQLite file under data/: daily counts per renter, and which renter owns which case.

It holds ids and counts only: no photos, no listing text, no sponsor data.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

DB_NAME = "safety.sqlite"


class SafetyStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / DB_NAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.execute(
                "create table if not exists checks"
                " (renter_id text, day text, n integer, primary key (renter_id, day))"
            )
            con.execute(
                "create table if not exists cases"
                " (case_id text primary key, renter_id text, created_at text)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def checks_on(self, renter_id: str, day: str) -> int:
        with closing(self._connect()) as con:
            row = con.execute(
                "select n from checks where renter_id = ? and day = ?", (renter_id, day)
            ).fetchone()
        return row[0] if row else 0

    def add_check(self, renter_id: str, day: str) -> None:
        with closing(self._connect()) as con, con:
            con.execute(
                "insert into checks values (?, ?, 1)"
                " on conflict (renter_id, day) do update set n = n + 1",
                (renter_id, day),
            )

    def register_case(self, case_id: str, renter_id: str) -> None:
        with closing(self._connect()) as con, con:
            con.execute(
                "insert or replace into cases values (?, ?, ?)",
                (case_id, renter_id, datetime.now(UTC).isoformat()),
            )

    def cases_of(self, renter_id: str) -> list[str]:
        with closing(self._connect()) as con:
            rows = con.execute(
                "select case_id from cases where renter_id = ? order by created_at", (renter_id,)
            ).fetchall()
        return [r[0] for r in rows]

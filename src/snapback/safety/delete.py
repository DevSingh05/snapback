"""The renter's "delete" command: their cases, the photos and every hash row, gone.

The photo memory (V5) keys rows by a keyed hash of the case id, so it is cleared through its own
`PhotoMemory.delete_case`. Any other SQLite file under data/ with a `case_id` column also loses
that case's rows, so a new store keyed by plain case id cannot be forgotten. Daily check counts
are kept: they hold no content, and deleting them would reset the limit.
"""

import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from snapback.safety.paths import resolve_data_dir
from snapback.safety.store import SafetyStore

CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DB_SUFFIXES = {".sqlite", ".sqlite3", ".db"}


@dataclass(frozen=True)
class DeleteReport:
    case_id: str
    rows: int  # database rows removed, across every store
    files: int  # files removed from data/cases/<case_id>/
    memory_cleared: bool = False  # the V5 photo memory store existed and dropped this case


def _databases(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        return []
    return sorted(p for p in data_dir.rglob("*") if p.is_file() and p.suffix in DB_SUFFIXES)


def _delete_rows(db: Path, case_id: str) -> int:
    removed = 0
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("pragma secure_delete = on")
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for table in tables:
            cols = [r[1] for r in con.execute(f'pragma table_info("{table}")')]
            if "case_id" in cols:
                cur = con.execute(f'delete from "{table}" where case_id = ?', (case_id,))
                removed += cur.rowcount
    return removed


def delete_case(case_id: str, data_dir: Path) -> DeleteReport:
    if not CASE_ID.match(case_id):
        raise ValueError("not a case id")
    data_dir = resolve_data_dir(data_dir)
    memory_db = data_dir / "memory" / "photo_memory.sqlite"
    memory_cleared = False
    if memory_db.is_file():
        from snapback.vision.memory import PhotoMemory

        PhotoMemory(memory_db).delete_case(case_id)
        memory_cleared = True
    rows = sum(_delete_rows(db, case_id) for db in _databases(data_dir) if db != memory_db)
    folder = data_dir / "cases" / case_id
    files = 0
    if folder.is_dir():
        files = sum(1 for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
    return DeleteReport(case_id, rows, files, memory_cleared)


def delete_renter(renter_id: str, data_dir: Path) -> list[str]:
    """Every case this renter started. Returns the case ids that were deleted."""
    case_ids = SafetyStore(data_dir).cases_of(renter_id)
    for case_id in case_ids:
        delete_case(case_id, data_dir)
    return case_ids

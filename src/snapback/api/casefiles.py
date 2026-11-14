"""A case's evidence files, kept in memory for the length of the session and served read-only.

What lives here: the evidence file the code wrote (`EvidenceFile`, shown in the "How we know"
drawer), the agent's working notes by path, and the two pictures behind each photo alias (the
ad's photo and the scan view it matched). The agent side (E1) attaches one `CaseFiles` to a
case as `case.files`; the routes in `api/main.py` only read it.

Pictures are case data, never written to disk here and never logged. Only JPEG bytes are ever
served, so a stored value that is not a JPEG answers 404.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from snapback.contracts import EvidenceFile

By = Literal["model", "policy", "code"]
ImageKind = Literal["photo", "scan"]

EVIDENCE_PATH = "evidence/photos.json"
_PATH = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*")
ALIAS = re.compile(r"[A-Z]\d{1,3}")
_JPEG_MAGIC = b"\xff\xd8\xff"


def safe_path(path: str) -> str | None:
    """The path if it is plain (letters, digits, `_ . -` and `/` between names, no climbing),
    else None. Lookups are by exact key, so this is a second wall, not the only one."""
    if not _PATH.fullmatch(path) or any(part in {".", ".."} for part in path.split("/")):
        return None
    return path


@dataclass
class CaseFiles:
    evidence: EvidenceFile | None = None
    notes: dict[str, tuple[str, By]] = field(default_factory=dict)  # path -> (text, written_by)
    images: dict[tuple[str, ImageKind], bytes] = field(default_factory=dict)

    def read(self, path: str) -> tuple[str, By] | None:
        """(text, written_by) of a file, or None. `evidence/photos.json` is the evidence file."""
        clean = safe_path(path)
        if clean is None:
            return None
        if clean == EVIDENCE_PATH and self.evidence is not None:
            return self.evidence.model_dump_json(indent=2), "code"
        return self.notes.get(clean)

    def image(self, alias: str, kind: ImageKind) -> bytes | None:
        data = self.images.get((alias, kind))
        return data if data is not None and data.startswith(_JPEG_MAGIC) else None

"""The case bank: labelled cases the harness scores.

One JSON object per line. Each case names a base evidence file in `fixtures/contracts/` and a
patch over it, so a synthetic case is a few lines and still parses as `ModuleEvidence`:

    {"case_id": "fx-ev-f01", "kind": "forged_reply", "attack": "screen", "synthetic": true,
     "split": "h0", "device": "fx-phone-c", "room": "fx-room-3",
     "base": "module_evidence_hold.json", "patch": {...}}

`device` and `room` say which phone took the reply and in which room, so the held-out split
can be held out honestly: no device and no room in H0 appears in dev (`check_holdout`).

Patches merge into dicts and replace lists. An injection case also carries `injected_patch`,
applied on top of the patched evidence: the same case with injected text seen somewhere.

Kinds:
- forged_reply: the reply photo is not a fresh photo at the spot (screen, print, paste, copy).
- genuine_reply: a fresh photo at the spot; any block is a false reject.
- injection: the gate case; the injected copy must get the same state as the plain one.
"""

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from snapback.contracts import ModuleEvidence

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_BANK = REPO_ROOT / "fixtures" / "eval" / "case_bank.jsonl"
CONTRACT_FIXTURES = REPO_ROOT / "fixtures" / "contracts"


class CaseKind(StrEnum):
    FORGED_REPLY = "forged_reply"
    GENUINE_REPLY = "genuine_reply"
    INJECTION = "injection"


class BankCase(BaseModel):
    case_id: str
    kind: CaseKind
    attack: str | None = None
    synthetic: bool
    split: str  # "dev", "h0" or "h1"
    device: str  # the phone that took the reply photo
    room: str  # the room it was taken in
    evidence: ModuleEvidence
    injected: ModuleEvidence | None = None


def merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for key, value in patch.items():
            out[key] = merge(base.get(key), value) if key in base else value
        return out
    return patch


def _case(row: dict[str, Any], bases_dir: Path) -> BankCase:
    base = json.loads((bases_dir / row["base"]).read_text())
    evidence = merge(base, row.get("patch", {}))
    evidence["case_id"] = row["case_id"]
    injected = None
    if row["kind"] == CaseKind.INJECTION and "injected_patch" not in row:
        raise ValueError(f"injection case {row['case_id']} has no injected_patch")
    if "injected_patch" in row:
        injected = merge(evidence, row["injected_patch"])
    return BankCase(
        case_id=row["case_id"],
        kind=row["kind"],
        attack=row.get("attack"),
        synthetic=row["synthetic"],
        split=row["split"],
        device=row["device"],
        room=row["room"],
        evidence=ModuleEvidence.model_validate(evidence),
        injected=None if injected is None else ModuleEvidence.model_validate(injected),
    )


def bank_digest(path: Path = FIXTURE_BANK, bases_dir: Path = CONTRACT_FIXTURES) -> str:
    """sha256 over the bank file and every base evidence file it names, so editing a base
    fixture changes the digest as surely as editing the bank."""
    digest = hashlib.sha256(Path(path).read_bytes())
    bases = set()
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            bases.add(json.loads(line)["base"])
    for name in sorted(bases):
        digest.update(name.encode())
        digest.update((bases_dir / name).read_bytes())
    return digest.hexdigest()


def load_bank(path: Path = FIXTURE_BANK, bases_dir: Path = CONTRACT_FIXTURES) -> list[BankCase]:
    cases = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            cases.append(_case(json.loads(line), bases_dir))
        except (ValueError, KeyError) as error:
            raise ValueError(f"{path.name} line {number}: {error}") from error
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: case ids repeat")
    return cases

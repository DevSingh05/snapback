"""Score the case bank under each condition, and gate on the results.

A condition decides which module outputs the verdict code may see:

- `rules_only`: the challenge's own checks (code read by OCR, reply placed at the spot).
- `rules_plus_model_<v>`: plus recapture results from model version v, and only those.
- `rules_plus_model_<v>_memory`: plus photo memory (latest model only, as the Lab panel shows).

Every number comes from `snapback.verdict`, so the harness measures the product as shipped.
"""

from collections.abc import Callable, Sequence

from snapback.contracts import MemoryHitKind, ModuleEvidence, PresenceStatus
from snapback.eval.bank import BankCase, CaseKind
from snapback.eval.results import ResultRow
from snapback.verdict import decide, presence_of, to_evidence

FORGED_FALSE_ACCEPT = "forged_false_accept"
GENUINE_FALSE_REJECT = "genuine_false_reject"
MEMORY_CATCH = "memory_catch"
COPY_ATTACK_PREFIX = "copy"  # attacks that reuse a listing photo: copy, copy_crop, ...

# Metrics where a higher rate is worse; the regression gate watches these.
GATED_METRICS = (FORGED_FALSE_ACCEPT,)

Condition = Callable[[ModuleEvidence], ModuleEvidence]


def _view(*, model: str | None, memory: bool) -> Condition:
    def view(evidence: ModuleEvidence) -> ModuleEvidence:
        recapture = [r for r in evidence.recapture if model and r.model_version == model]
        return evidence.model_copy(
            update={"recapture": recapture, "memory": evidence.memory if memory else []}
        )

    return view


def conditions(models: Sequence[str]) -> dict[str, Condition]:
    out: dict[str, Condition] = {"rules_only": _view(model=None, memory=False)}
    for model in models:
        out[f"rules_plus_model_{model}"] = _view(model=model, memory=False)
    if models:
        out[f"rules_plus_model_{models[-1]}_memory"] = _view(model=models[-1], memory=True)
    return out


def _accepted(evidence: ModuleEvidence) -> bool:
    return presence_of(evidence).status is PresenceStatus.PROVEN


def evaluate(
    cases: Sequence[BankCase],
    models: Sequence[str],
    *,
    split: str | None = "h0",
    frozen_at: str,
) -> list[ResultRow]:
    """Rows for results.csv. `split=None` scores every case (dev runs only, never quoted)."""
    scored = [case for case in cases if split is None or case.split == split]
    forged = [case.evidence for case in scored if case.kind is CaseKind.FORGED_REPLY]
    genuine = [case.evidence for case in scored if case.kind is CaseKind.GENUINE_REPLY]

    rows = []
    for name, view in conditions(models).items():
        if forged:
            k = sum(_accepted(view(evidence)) for evidence in forged)
            rows.append(ResultRow.measure(name, FORGED_FALSE_ACCEPT, k, len(forged), frozen_at))
        if genuine and name != "rules_only":
            k = sum(not _accepted(view(evidence)) for evidence in genuine)
            rows.append(ResultRow.measure(name, GENUINE_FALSE_REJECT, k, len(genuine), frozen_at))

    copies = [
        case.evidence
        for case in scored
        if case.kind is CaseKind.FORGED_REPLY and (case.attack or "").startswith(COPY_ATTACK_PREFIX)
    ]
    if copies:
        caught = sum(
            any(hit.hit is MemoryHitKind.SAME_CASE_LISTING for hit in evidence.memory)
            for evidence in copies
        )
        rows.append(ResultRow.measure("memory", MEMORY_CATCH, caught, len(copies), frozen_at))
    return rows


def check_injections(cases: Sequence[BankCase]) -> list[str]:
    """One failure line per injection case whose injected copy gets a different state."""
    failures = []
    for case in cases:
        if case.kind is not CaseKind.INJECTION or case.injected is None:
            continue
        plain = decide(to_evidence(case.evidence)).state
        injected = decide(to_evidence(case.injected)).state
        if plain is not injected:
            failures.append(
                f"injection case {case.case_id} changed the state: "
                f"{plain.value} without the injection, {injected.value} with it"
            )
    return failures


def check_regression(rows: Sequence[ResultRow], baseline: Sequence[ResultRow]) -> list[str]:
    """One failure line per gated (condition, metric) whose rate rose over the baseline."""
    before = {(row.condition, row.metric): row for row in baseline}
    failures = []
    for row in rows:
        old = before.get((row.condition, row.metric))
        if row.metric in GATED_METRICS and old is not None and row.rate > old.rate:
            failures.append(
                f"{row.condition} {row.metric} rose from {old.rate:.4f} (n={old.n}) "
                f"to {row.rate:.4f} (n={row.n})"
            )
    return failures

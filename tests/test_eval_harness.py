"""Eval harness (V6): the only source of numbers we quote, and the CI gate over them."""

import csv
import json
from pathlib import Path

import pytest

from snapback.contracts import VerdictState
from snapback.eval import (
    RESULTS_COLUMNS,
    BankCase,
    CaseKind,
    ResultRow,
    check_injections,
    check_regression,
    evaluate,
    load_bank,
    read_results,
    wilson,
    write_results,
)
from snapback.eval.__main__ import main

REPO = Path(__file__).resolve().parent.parent
BANK = REPO / "fixtures" / "eval" / "case_bank.jsonl"
SAMPLE = REPO / "fixtures" / "contracts" / "results_sample.csv"


# --- Wilson interval ---------------------------------------------------------------------------


def test_wilson_interval_matches_known_values():
    # Rows of the T6 sample, which were computed by hand with z = 1.96.
    assert wilson(9, 40) == pytest.approx((0.1232, 0.3750), abs=1e-4)
    assert wilson(12, 15) == pytest.approx((0.5481, 0.9295), abs=1e-4)
    assert wilson(1, 40) == pytest.approx((0.0044, 0.1288), abs=1e-4)


def test_wilson_edges():
    low, high = wilson(0, 20)
    assert low == 0.0 and 0.0 < high < 0.2
    low, high = wilson(20, 20)
    assert 0.8 < low < 1.0 and high == pytest.approx(1.0)
    with pytest.raises(ValueError):
        wilson(1, 0)
    with pytest.raises(ValueError):
        wilson(5, 4)


# --- results.csv -------------------------------------------------------------------------------


def test_results_csv_has_the_t6_columns_and_round_trips(tmp_path):
    rows = [ResultRow.measure("rules_only", "forged_false_accept", 9, 40, frozen_at="FIXTURE")]
    path = tmp_path / "results.csv"
    write_results(rows, path, comment="FIXTURE: test rows")

    lines = path.read_text().splitlines()
    assert lines[0] == "# FIXTURE: test rows"
    assert lines[1] == ",".join(RESULTS_COLUMNS)
    assert lines[1] == "condition,metric,k,n,rate,ci_low,ci_high,frozen_at"
    assert lines[2] == "rules_only,forged_false_accept,9,40,0.2250,0.1232,0.3750,FIXTURE"
    assert read_results(path) == rows


def test_reads_the_t6_sample():
    rows = read_results(SAMPLE)
    assert len(rows) == 11
    assert rows[0].condition == "rules_only" and rows[0].n == 40


# --- the case bank -----------------------------------------------------------------------------


def test_fixture_bank_loads_and_is_synthetic():
    cases = load_bank(BANK)
    assert {case.kind for case in cases} == set(CaseKind)
    assert all(case.synthetic for case in cases)
    assert all(case.case_id.startswith("fx-") for case in cases)
    injection = next(case for case in cases if case.kind is CaseKind.INJECTION)
    assert injection.injected is not None


def test_conditions_see_only_their_own_modules():
    cases = load_bank(BANK)
    rows = {(r.condition, r.metric): r for r in evaluate(cases, ["v0"], frozen_at="FIXTURE")}

    rules_only = rows[("rules_only", "forged_false_accept")]
    with_model = rows[("rules_plus_model_v0", "forged_false_accept")]
    with_memory = rows[("rules_plus_model_v0_memory", "forged_false_accept")]
    assert rules_only.n == with_model.n == with_memory.n > 0
    # Each module can only take a pass away, so each step catches at least as much.
    assert rules_only.k >= with_model.k >= with_memory.k
    assert with_memory.k < rules_only.k
    assert ("rules_plus_model_v0", "genuine_false_reject") in rows


def test_only_the_requested_split_is_counted():
    cases = load_bank(BANK)
    h0 = evaluate(cases, ["v0"], split="h0", frozen_at="x")
    every = evaluate(cases, ["v0"], split=None, frozen_at="x")
    n_h0 = next(r.n for r in h0 if r.metric == "forged_false_accept")
    n_all = next(r.n for r in every if r.metric == "forged_false_accept")
    assert 0 < n_h0 < n_all


# --- the gate ----------------------------------------------------------------------------------


def _injection(case_id: str, injected_presence: str) -> BankCase:
    cases = load_bank(BANK)
    base = next(case for case in cases if case.kind is CaseKind.INJECTION)
    injected = base.injected.model_copy(deep=True)
    injected.challenge = injected.challenge.model_copy(update={"presence": injected_presence})
    return base.model_copy(update={"case_id": case_id, "injected": injected})


def test_injection_case_state_change_fails_gate():
    holding = _injection("fx-inj-holds", "waiting")
    flipped = _injection("fx-inj-flips", "forged")

    assert check_injections([holding]) == []
    failures = check_injections([holding, flipped])
    assert len(failures) == 1
    assert "fx-inj-flips" in failures[0]
    assert VerdictState.DONT_PAY.value in failures[0]


def test_false_accept_rise_fails_gate():
    baseline = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "a")]
    same = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "b")]
    worse = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 6, 40, "b")]
    better = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 2, 40, "b")]

    assert check_regression(same, baseline) == []
    assert check_regression(better, baseline) == []
    failures = check_regression(worse, baseline)
    assert len(failures) == 1 and "rules_plus_model_v0" in failures[0]


def test_fixture_bank_passes_the_gate():
    """The CI gate: no injection case in the committed bank changes a state."""
    assert check_injections(load_bank(BANK)) == []


# --- the command -------------------------------------------------------------------------------


def test_command_writes_results_and_passes(tmp_path, capsys):
    out = tmp_path / "results.csv"
    assert main(["--bank", str(BANK), "--out", str(out), "--models", "v0", "v1"]) == 0
    rows = read_results(out)
    assert {r.condition for r in rows} >= {"rules_only", "rules_plus_model_v1_memory"}
    assert all(r.frozen_at == "FIXTURE" for r in rows)
    assert out.read_text().startswith("# FIXTURE")
    assert "gate: ok" in capsys.readouterr().out


def test_command_fails_on_regression_against_baseline(tmp_path):
    baseline = tmp_path / "baseline.csv"
    with baseline.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(RESULTS_COLUMNS)
        writer.writerow(["rules_only", "forged_false_accept", 0, 4, "0.0000", 0, 0.49, "old"])
    out = tmp_path / "results.csv"
    code = main(["--bank", str(BANK), "--out", str(out), "--baseline", str(baseline)])
    assert code == 1


def test_bank_rows_are_plain_json_lines():
    for line in BANK.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            json.loads(line)

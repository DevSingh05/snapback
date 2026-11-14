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
    check_holdout,
    check_injections,
    check_regression,
    evaluate,
    load_bank,
    read_meta,
    read_results,
    wilson,
    write_results,
)
from snapback.eval.__main__ import DEFAULT_OUT, main

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
    same = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "a")]
    worse = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 6, 40, "a")]
    better = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 2, 40, "a")]

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
    # The bank's rows say FIXTURE; calibration rows (renders) carry their own version tag.
    bank_rows = [r for r in rows if r.condition != "place_real_renders"]
    assert bank_rows and all(r.frozen_at == "FIXTURE" for r in bank_rows)
    assert out.read_text().startswith("# FIXTURE")
    assert "gate: ok" in capsys.readouterr().out


def test_command_fails_on_regression_against_baseline(tmp_path):
    baseline = tmp_path / "baseline.csv"
    with baseline.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(RESULTS_COLUMNS)
        writer.writerow(["rules_only", "forged_false_accept", 0, 4, "0.0000", 0, 0.49, "FIXTURE"])
    out = tmp_path / "results.csv"
    code = main(["--bank", str(BANK), "--out", str(out), "--baseline", str(baseline)])
    assert code == 1


def test_bank_rows_are_plain_json_lines():
    for line in BANK.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            json.loads(line)


# --- review fixes (#62) ------------------------------------------------------------------------


def test_requested_model_with_no_results_raises():
    cases = load_bank(BANK)
    with pytest.raises(ValueError, match="V1"):
        evaluate(cases, ["v0", "V1"], frozen_at="FIXTURE")


def test_command_refuses_a_phantom_model(tmp_path, capsys):
    out = tmp_path / "results.csv"
    assert main(["--bank", str(BANK), "--out", str(out), "--models", "v0", "v9"]) == 2
    assert not out.exists()
    assert "v9" in capsys.readouterr().out


def test_exactly_one_memory_row_for_the_latest_model():
    rows = evaluate(load_bank(BANK), ["v0", "v1"], frozen_at="FIXTURE")
    memory = {r.condition for r in rows if r.condition.endswith("_memory")}
    assert memory == {"rules_plus_model_v1_memory"}


def test_gate_fails_when_a_gated_row_goes_missing():
    baseline = [
        ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "a"),
        ResultRow.measure("rules_plus_model_v1", "forged_false_accept", 3, 40, "a"),
    ]
    run = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "a")]
    failures = check_regression(run, baseline)
    assert len(failures) == 1 and "rules_plus_model_v1" in failures[0] and "missing" in failures[0]


def test_gate_fails_when_frozen_at_changes():
    baseline = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 4, 40, "h0-a")]
    run = [ResultRow.measure("rules_plus_model_v0", "forged_false_accept", 1, 40, "h0-b")]
    failures = check_regression(run, baseline)
    assert len(failures) == 1 and "frozen_at" in failures[0]


def test_gate_fails_when_the_split_changes(tmp_path):
    rows = [ResultRow.measure("rules_only", "forged_false_accept", 1, 4, "FIXTURE")]
    write_results(rows, tmp_path / "a.csv", comment="x", meta={"split": "h0"})
    write_results(rows, tmp_path / "b.csv", comment="x", meta={"split": "all"})
    assert read_meta(tmp_path / "a.csv") == {"split": "h0"}
    failures = check_regression(
        rows, rows, meta=read_meta(tmp_path / "b.csv"), baseline_meta=read_meta(tmp_path / "a.csv")
    )
    assert len(failures) == 1 and "split" in failures[0]


def test_injection_case_without_injected_patch_is_rejected(tmp_path):
    bank = tmp_path / "bank.jsonl"
    row = {
        "case_id": "fx-i",
        "kind": "injection",
        "synthetic": True,
        "split": "h0",
        "device": "fx-phone-c",
        "room": "fx-room-3",
        "base": "module_evidence_hold.json",
    }
    bank.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="injected_patch"):
        load_bank(bank)


def test_bank_cases_carry_device_and_room():
    cases = load_bank(BANK)
    assert all(case.device and case.room for case in cases)


def test_holdout_shares_no_device_or_room_with_dev():
    assert check_holdout(load_bank(BANK)) == []
    cases = load_bank(BANK)
    dev = next(case for case in cases if case.split == "dev")
    leaky = [*cases, dev.model_copy(update={"case_id": "fx-leak", "split": "h0"})]
    failures = check_holdout(leaky)
    assert failures and all("fx-leak" not in f or "dev" in f for f in failures)


def test_results_are_written_where_the_api_reads_them():
    assert DEFAULT_OUT.parts[-2:] == ("eval", "results.csv")


def test_committed_results_pass_the_gate_against_the_frozen_baseline(tmp_path):
    """What CI runs: the harness on the committed bank, gated on eval/baseline.csv."""
    baseline = REPO / "eval" / "baseline.csv"
    out = tmp_path / "results.csv"
    assert main(["--bank", str(BANK), "--out", str(out), "--baseline", str(baseline)]) == 0
    assert read_results(REPO / "eval" / "results.csv") == read_results(out)


# --- second review (#62): bank padding, write only after the gate --------------------------------


def _padded_bank(tmp_path) -> Path:
    """The bank plus three copies of a forged case every condition catches, so no rate rises:
    only the bank-hash and n guards can fail the run."""
    lines = BANK.read_text().splitlines()
    caught = next(line for line in lines if '"fx-ev-f06"' in line)  # rejected under every condition
    extra = [caught.replace('"fx-ev-f06"', f'"fx-ev-f06-copy{i}"') for i in range(3)]
    padded = tmp_path / "padded.jsonl"
    padded.write_text("\n".join([*lines, *extra]) + "\n")
    return padded


def test_padding_the_bank_fails_the_gate(tmp_path):
    baseline = REPO / "eval" / "baseline.csv"
    code = main(
        [
            "--bank",
            str(_padded_bank(tmp_path)),
            "--out",
            str(tmp_path / "r.csv"),
            "--baseline",
            str(baseline),
        ]
    )
    assert code == 1


def test_gate_names_a_changed_bank_and_changed_n():
    rows = [ResultRow.measure("rules_only", "forged_false_accept", 6, 7, "FIXTURE")]
    padded = [ResultRow.measure("rules_only", "forged_false_accept", 6, 10, "FIXTURE")]
    failures = check_regression(
        padded,
        rows,
        meta={"split": "h0", "bank_sha256": "b"},
        baseline_meta={"split": "h0", "bank_sha256": "a"},
    )
    assert any("bank" in f for f in failures)
    assert any("n changed" in f for f in failures)


def test_a_failed_gate_leaves_the_results_file_untouched(tmp_path):
    out = tmp_path / "results.csv"
    out.write_text("previous results\n")
    code = main(
        [
            "--bank",
            str(_padded_bank(tmp_path)),
            "--out",
            str(out),
            "--baseline",
            str(REPO / "eval" / "baseline.csv"),
        ]
    )
    assert code == 1
    assert out.read_text() == "previous results\n"
    assert not list(tmp_path.glob(".results.csv.*"))  # no temp file left behind


def test_meta_records_the_bank_hash(tmp_path):
    out = tmp_path / "results.csv"
    assert main(["--bank", str(BANK), "--out", str(out)]) == 0
    meta = read_meta(out)
    assert len(meta["bank_sha256"]) == 64


# --- third review (#62): LIVE only when every scored case is real -------------------------------


def _bank_with(tmp_path, *, real_ids: set[str]) -> Path:
    """The fixture bank with the named cases marked real (synthetic false)."""
    out = []
    for line in BANK.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            row = json.loads(line)
            if row["case_id"] in real_ids:
                row["synthetic"] = False
            line = json.dumps(row)
        out.append(line)
    path = tmp_path / "bank.jsonl"
    path.write_text("\n".join(out) + "\n")
    return path


def test_a_mixed_scored_set_is_refused(tmp_path, capsys):
    bank = _bank_with(tmp_path, real_ids={"fx-ev-f01"})  # one real h0 case among synthetic ones
    out = tmp_path / "results.csv"
    assert main(["--bank", str(bank), "--out", str(out)]) == 2
    assert not out.exists()
    assert "synthetic" in capsys.readouterr().out


def test_label_comes_from_the_scored_cases_not_the_whole_bank(tmp_path):
    # A real case in dev is not scored on h0: the h0 run is still FIXTURE.
    bank = _bank_with(tmp_path, real_ids={"fx-ev-f08"})
    out = tmp_path / "results.csv"
    assert main(["--bank", str(bank), "--out", str(out)]) == 0
    assert out.read_text().startswith("# FIXTURE")
    bank_rows = [r for r in read_results(out) if r.condition != "place_real_renders"]
    assert bank_rows and all(row.frozen_at == "FIXTURE" for row in bank_rows)


def test_live_only_when_every_scored_case_is_real(tmp_path):
    h0 = [
        json.loads(line)["case_id"]
        for line in BANK.read_text().splitlines()
        if line.strip() and not line.startswith("#") and json.loads(line)["split"] == "h0"
    ]
    bank = _bank_with(tmp_path, real_ids=set(h0))
    out = tmp_path / "results.csv"
    assert main(["--bank", str(bank), "--out", str(out), "--frozen-at", "h0-test"]) == 0
    assert out.read_text().startswith("# LIVE")


def test_bank_hash_covers_the_base_fixtures(tmp_path):
    import shutil

    from snapback.eval.bank import bank_digest

    bases = tmp_path / "bases"
    shutil.copytree(REPO / "fixtures" / "contracts", bases)
    before = bank_digest(BANK, bases)
    (bases / "module_evidence_hold.json").write_text(
        (bases / "module_evidence_hold.json").read_text().replace('"proven"', '"waiting"', 1)
    )
    assert bank_digest(BANK, bases) != before


# --- #93: calibration_bin rows from the locate calibration --------------------------------------


def _calibration(tmp_path) -> Path:
    path = tmp_path / "locate_calibration.json"
    path.write_text(
        json.dumps(
            {
                "source": "renders: unseen directions from the indexed scan points, not photos",
                "version": "cal-test",
                "n_fit": 40,
                "n_test": 40,
                "bins": [
                    {"low": 0.0, "high": 0.1, "k": 1, "n": 30},
                    {"low": 0.9, "high": 1.0, "k": 9, "n": 10},
                ],
            }
        )
    )
    return path


def test_calibration_rows_use_the_lab_schema(tmp_path):
    from snapback.eval.harness import calibration_rows

    rows = calibration_rows(_calibration(tmp_path))
    assert [r.metric for r in rows] == ["calibration_bin:0.00-0.10", "calibration_bin:0.90-1.00"]
    assert all(r.condition == "place_real_renders" and r.frozen_at == "cal-test" for r in rows)
    assert (rows[1].k, rows[1].n) == (9, 10)


def test_command_appends_calibration_rows_and_says_where_they_came_from(tmp_path):
    out = tmp_path / "results.csv"
    assert (
        main(["--bank", str(BANK), "--out", str(out), "--calibration", str(_calibration(tmp_path))])
        == 0
    )
    text = out.read_text()
    assert "# calibration rows: renders" in text
    assert any(r.metric.startswith("calibration_bin:") for r in read_results(out))
    assert text.startswith("# FIXTURE")  # the bank's own rows keep their label


def test_no_calibration_file_means_no_calibration_rows(tmp_path):
    out = tmp_path / "results.csv"
    assert (
        main(["--bank", str(BANK), "--out", str(out), "--calibration", str(tmp_path / "none.json")])
        == 0
    )
    assert not any(r.metric.startswith("calibration_bin:") for r in read_results(out))

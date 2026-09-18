"""Runs the optimizer and validator against all ten public sample cases."""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy_optimizer import (  # noqa: E402
    TOLERANCE,
    build_response,
    optimize,
    replay_validate,
    resolve,
    validate_interpretation,
)

PACK = Path(__file__).resolve().parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
CASES = json.loads(PACK.read_text())["cases"]
IDS = [c["id"] for c in CASES]


@pytest.fixture(params=CASES, ids=IDS)
def case(request):
    return copy.deepcopy(request.param)


# --- calibration: the validator must agree with the official answers ---------


def test_reference_schedule_passes_replay(case):
    """If this fails the validator is wrong, not the reference."""
    truth = resolve(case["expected_output"]["directive_interpretation"])
    report = replay_validate(case["input"], truth, case["expected_output"])
    assert report.ok, f"{case['id']}\n{report}"


def test_reference_interpretation_passes_schema(case):
    errs = validate_interpretation(
        case["expected_output"]["directive_interpretation"],
        len(case["input"]["operator_notes"]),
    )
    assert not errs, f"{case['id']}: {errs}"


# --- the optimizer ----------------------------------------------------------


def test_optimized_plan_is_valid(case):
    truth = resolve(case["expected_output"]["directive_interpretation"])
    solution = optimize(case["input"], truth)
    assert solution.status == "optimal", f"{case['id']} relaxed {solution.relaxed}"

    response = {
        "scenario_id": case["input"]["scenario_id"],
        "hourly_plan": solution.hourly_plan,
        "total_grid_kwh": None,
        "total_cost_bdt": None,
        "peak_grid_kwh": None,
    }
    report = replay_validate(case["input"], truth, response)
    structural = [v for v in report.violations if v.kind != "totals"]
    assert not structural, f"{case['id']}\n" + "\n".join(str(v) for v in structural)


def test_cost_matches_or_beats_reference(case):
    truth = resolve(case["expected_output"]["directive_interpretation"])
    solution = optimize(case["input"], truth)
    response = {
        "scenario_id": case["input"]["scenario_id"],
        "hourly_plan": solution.hourly_plan,
        "total_grid_kwh": None,
        "total_cost_bdt": None,
        "peak_grid_kwh": None,
    }
    mine = replay_validate(case["input"], truth, response).total_cost_bdt
    reference = case["expected_output"]["total_cost_bdt"]
    assert mine <= reference + TOLERANCE, (
        f"{case['id']}: {mine:.2f} BDT vs reference {reference:.2f}"
    )


# --- the full response ------------------------------------------------------


def test_build_response_is_self_consistent(case):
    interpretation = case["expected_output"]["directive_interpretation"]
    response = build_response(case["input"], interpretation)

    truth = resolve(interpretation)
    report = replay_validate(case["input"], truth, response)
    assert report.ok, f"{case['id']}\n{report}"
    assert response["scenario_id"] == case["input"]["scenario_id"]
    assert len(response["hourly_plan"]) == 24


def test_idle_hours_carry_exactly_zero(case):
    response = build_response(case["input"], case["expected_output"]["directive_interpretation"])
    for row in response["hourly_plan"]:
        if row["battery_action"] == "idle":
            assert row["battery_kwh"] == 0, row


def test_solves_well_inside_the_latency_budget(case):
    truth = resolve(case["expected_output"]["directive_interpretation"])
    start = time.perf_counter()
    optimize(case["input"], truth)
    assert (time.perf_counter() - start) < 0.5


# --- the validator must actually catch things -------------------------------


def _corrupt(case, hour, **changes):
    response = copy.deepcopy(case["expected_output"])
    response["hourly_plan"][hour].update(changes)
    truth = resolve(case["expected_output"]["directive_interpretation"])
    return replay_validate(case["input"], truth, response)


def test_detects_broken_energy_balance():
    report = _corrupt(CASES[0], 5, grid_kwh=CASES[0]["expected_output"]["hourly_plan"][5]["grid_kwh"] + 7)
    assert "energy_balance" in {v.kind for v in report.violations}


def test_detects_soc_drift_and_neutrality_break():
    report = _corrupt(CASES[0], 5, battery_action="charge", battery_kwh=20)
    kinds = {v.kind for v in report.violations}
    assert {"soc_drift", "neutrality"} <= kinds


def test_detects_nonzero_idle():
    report = _corrupt(CASES[0], 0, battery_kwh=1e-9)
    assert "action_consistency" in {v.kind for v in report.violations}


def test_detects_solar_overuse():
    case = CASES[0]  # hours 12-13 are reduced to 25%
    report = _corrupt(case, 12, solar_used_kwh=180, grid_kwh=-45)
    assert "solar_overuse" in {v.kind for v in report.violations}


def test_detects_window_violations():
    case = CASES[1]  # no_charge_window on hours 2, 3, 4
    report = _corrupt(case, 3, battery_action="charge", battery_kwh=10)
    assert "no_charge_window" in {v.kind for v in report.violations}

    case = CASES[3]  # no_discharge_window on hours 18, 19
    report = _corrupt(case, 18, battery_action="discharge", battery_kwh=10)
    assert "no_discharge_window" in {v.kind for v in report.violations}


def test_detects_grid_cap_breach():
    case = CASES[4]  # max_grid_window 155 on hours 18, 19, 20
    report = _corrupt(case, 19, grid_kwh=200)
    assert "max_grid_window" in {v.kind for v in report.violations}


def test_detects_reserve_breach():
    case = CASES[2]  # reserve 100 kWh on hours 18, 19, 20
    response = copy.deepcopy(case["expected_output"])
    for hour in range(18, 21):
        response["hourly_plan"][hour].update(
            battery_action="discharge", battery_kwh=50
        )
    truth = resolve(case["expected_output"]["directive_interpretation"])
    report = replay_validate(case["input"], truth, response)
    assert "soc_below_floor" in {v.kind for v in report.violations}


def test_detects_stale_totals():
    case = CASES[0]
    response = copy.deepcopy(case["expected_output"])
    response["total_cost_bdt"] = 1.0
    truth = resolve(case["expected_output"]["directive_interpretation"])
    report = replay_validate(case["input"], truth, response)
    assert "totals" in {v.kind for v in report.violations}


# --- resolve ----------------------------------------------------------------


def test_resolve_ignores_no_op_and_keeps_the_strictest_overlap():
    directives = resolve(
        [
            {"note_index": 0, "applies": False, "directive_type": "no_op", "structured_adjustment": None},
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [10, 11], "factor": 0.5},
            },
            {
                "note_index": 2,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [11], "factor": 0.2},
            },
        ]
    )
    assert directives.effective_solar(10, 100) == 50
    assert directives.effective_solar(11, 100) == 20
    assert directives.effective_solar(12, 100) == 100


def test_interpretation_schema_rejects_malformed_entries():
    assert validate_interpretation([], 1)
    assert validate_interpretation(
        [{"note_index": 0, "applies": True, "directive_type": "no_op",
          "structured_adjustment": None, "explanation": "x"}], 1
    )
    assert validate_interpretation(
        [{"note_index": 0, "applies": True, "directive_type": "solar_reduction",
          "structured_adjustment": {"hours": [13, 12], "factor": 0.2}, "explanation": "x"}], 1
    )
    assert validate_interpretation(
        [{"note_index": 0, "applies": True, "directive_type": "max_grid_window",
          "structured_adjustment": {"hours": [1]}, "explanation": "x"}], 1
    )

"""Regression suite over the adversarial cases in tricky_cases/.

Ground truth here is locked to disk, so these fail if a change to resolve(),
the optimizer or the validator alters any stored schedule or cost.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from energy_optimizer import (  # noqa: E402
    TOLERANCE,
    build_response,
    optimize,
    replay_validate,
    resolve,
    validate_interpretation,
)
from tools.dp_oracle import dp_optimal_cost  # noqa: E402

CASE_DIR = ROOT / "tricky_cases"
CASES = [json.loads(p.read_text()) for p in sorted(CASE_DIR.glob("TRICKY-*.json"))]
IDS = [c["id"] for c in CASES]

assert len(CASES) == 10, f"expected 10 tricky cases, found {len(CASES)}"


@pytest.fixture(params=CASES, ids=IDS)
def case(request):
    return copy.deepcopy(request.param)


def _plan_probe(case_id, plan):
    return {
        "scenario_id": case_id,
        "hourly_plan": plan,
        "total_grid_kwh": None,
        "total_cost_bdt": None,
        "peak_grid_kwh": None,
    }


def test_stored_ground_truth_still_replays_clean(case):
    truth = resolve(case["expected_output"]["directive_interpretation"])
    report = replay_validate(case["input"], truth, case["expected_output"])
    assert report.ok, f"{case['id']}\n{report}"


def test_interpretation_matches_schema(case):
    errs = validate_interpretation(
        case["expected_output"]["directive_interpretation"],
        len(case["input"]["operator_notes"]),
    )
    assert not errs, f"{case['id']}: {errs}"


def test_pipeline_reproduces_the_stored_cost(case):
    response = build_response(case["input"], case["expected_output"]["directive_interpretation"])
    assert response["total_cost_bdt"] == pytest.approx(
        case["expected_output"]["total_cost_bdt"], abs=TOLERANCE
    )


def test_directives_are_feasible_as_authored(case):
    truth = resolve(case["expected_output"]["directive_interpretation"])
    solution = optimize(case["input"], truth)
    assert solution.status == "optimal", f"{case['id']} relaxed {solution.relaxed}"


def test_dp_oracle_confirms_optimality(case):
    """Independent algorithm, same answer."""
    truth = resolve(case["expected_output"]["directive_interpretation"])
    dp_cost = dp_optimal_cost(case["input"], truth)
    lp_cost = case["expected_output"]["total_cost_bdt"]
    assert dp_cost == pytest.approx(lp_cost, abs=TOLERANCE), (
        f"{case['id']}: DP {dp_cost:.2f} vs LP {lp_cost:.2f}"
    )


def test_case_still_punishes_the_documented_misreading(case):
    """The trap must stay live: a decoy plan has to be invalid or costlier."""
    decoy_interp = case.get("decoy")
    if decoy_interp is None:
        pytest.skip("decoy not stored on disk")

    truth = resolve(case["expected_output"]["directive_interpretation"])
    decoy_plan = optimize(case["input"], resolve(decoy_interp)).hourly_plan
    judged = replay_validate(case["input"], truth, _plan_probe(case["id"], decoy_plan))

    breaks = [v for v in judged.violations if v.kind != "totals"]
    penalty = judged.total_cost_bdt - case["expected_output"]["total_cost_bdt"]
    assert breaks or penalty > TOLERANCE, (
        f"{case['id']}: the misreading '{case.get('decoy_why')}' goes unpunished"
    )

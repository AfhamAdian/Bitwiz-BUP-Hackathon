"""Run the pipeline against every tricky_cases/*.json and store results.

For each case: feed input + the stored ground-truth directive_interpretation
into build_response(), replay-validate the result against ground truth, and
write a result file to tricky_cases/results/<ID>.json comparing our output
to the stored expected_output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from energy_optimizer import TOLERANCE, build_response, replay_validate, resolve  # noqa: E402

CASE_DIR = ROOT / "tricky_cases"
RESULT_DIR = CASE_DIR / "results"


def schedule_diff(ours: list[dict], theirs: list[dict]) -> list[int]:
    return [
        t
        for t, (a, b) in enumerate(zip(ours, theirs))
        if abs(a["grid_kwh"] - b["grid_kwh"]) > TOLERANCE
        or a["battery_action"] != b["battery_action"]
        or abs(a["battery_kwh"] - b["battery_kwh"]) > TOLERANCE
    ]


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    cases = sorted(CASE_DIR.glob("TRICKY-*.json"))
    failures = 0

    print(f"{'case':11} {'our cost':>11} {'expected':>11} {'delta':>8}  {'hours diff':>10}  valid  match")
    print("-" * 72)

    for path in cases:
        case = json.loads(path.read_text())
        request = case["input"]
        expected = case["expected_output"]
        interpretation = expected["directive_interpretation"]

        response = build_response(request, interpretation)
        truth = resolve(interpretation)
        report = replay_validate(request, truth, response)

        delta = response["total_cost_bdt"] - expected["total_cost_bdt"]
        diff_hours = schedule_diff(response["hourly_plan"], expected["hourly_plan"])
        cost_matches = abs(delta) <= TOLERANCE
        is_match = report.ok and cost_matches

        if not is_match:
            failures += 1

        print(
            f"{case['id']:11} {response['total_cost_bdt']:11,.2f} "
            f"{expected['total_cost_bdt']:11,.2f} {delta:+8.2f}  "
            f"{len(diff_hours):10}  {report.ok!s:5}  {'YES' if is_match else 'NO'}"
        )
        if not report.ok:
            for v in report.violations:
                print(f"            ! {v}")

        result = {
            "id": case["id"],
            "label": case["label"],
            "our_response": response,
            "expected_output": expected,
            "comparison": {
                "cost_matches_within_tolerance": cost_matches,
                "our_cost_bdt": response["total_cost_bdt"],
                "expected_cost_bdt": expected["total_cost_bdt"],
                "delta_bdt": round(delta, 4),
                "replay_valid_against_ground_truth": report.ok,
                "replay_violations": [str(v) for v in report.violations],
                "schedule_differs_at_hours": diff_hours,
                "verdict": "MATCH" if is_match else "MISMATCH",
            },
        }
        (RESULT_DIR / f"{case['id']}.json").write_text(json.dumps(result, indent=2) + "\n")

    print("-" * 72)
    print(f"{len(cases) - failures}/{len(cases)} match, results written to {RESULT_DIR.relative_to(ROOT)}/")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

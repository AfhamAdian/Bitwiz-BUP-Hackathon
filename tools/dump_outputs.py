"""Write one /optimize-energy response JSON per public sample case.

Directives come from each case's ground-truth interpretation, so these files
exercise the optimizer and validator only — the LLM half is not involved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gridwise import build_response, replay_validate, resolve  # noqa: E402

PACK = ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
OUT_DIR = ROOT / "outputs"


def main() -> int:
    cases = json.loads(PACK.read_text())["cases"]
    OUT_DIR.mkdir(exist_ok=True)

    failures = 0
    for case in cases:
        request = case["input"]
        expected = case["expected_output"]

        response = build_response(request, expected["directive_interpretation"])
        report = replay_validate(request, resolve(expected["directive_interpretation"]), response)

        path = OUT_DIR / f"{case['id']}.json"
        path.write_text(json.dumps(response, indent=2) + "\n")

        delta = response["total_cost_bdt"] - expected["total_cost_bdt"]
        status = "ok" if report.ok and delta <= 0.01 else "FAIL"
        if status == "FAIL":
            failures += 1
            print(report, file=sys.stderr)

        print(
            f"{status:4} {case['id']:10} {path.relative_to(ROOT)!s:22} "
            f"cost {response['total_cost_bdt']:>10,.2f}  "
            f"vs reference {expected['total_cost_bdt']:>10,.2f}  ({delta:+.2f})"
        )

    print(f"\n{len(cases) - failures}/{len(cases)} valid, written to {OUT_DIR.relative_to(ROOT)}/")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

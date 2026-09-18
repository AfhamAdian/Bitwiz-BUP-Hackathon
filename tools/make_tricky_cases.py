"""Generate ten adversarial GridWise cases with verified ground truth.

Each case pairs an interpretation trap (wording that defeats naive keyword
matching) with an optimizer stress (a binding constraint that defeats greedy
merit-order scheduling).

Ground truth has two independently-sourced halves:
  - directive_interpretation is hand-authored. The note was written to mean
    exactly this, so it is a genuine label rather than a model's guess.
  - hourly_plan comes from the LP, then is cross-checked against a DP oracle
    (a different algorithm) and replayed through the validator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gridwise import build_response, optimize, replay_validate, resolve  # noqa: E402
from gridwise.directives import validate_interpretation  # noqa: E402
from tools.dp_oracle import dp_optimal_cost  # noqa: E402

OUT_DIR = ROOT / "tricky_cases"

THIRD = round(1 / 3, 4)


def note(index, dtype, adjustment, explanation, applies=True):
    return {
        "note_index": index,
        "applies": applies,
        "directive_type": dtype,
        "structured_adjustment": adjustment,
        "explanation": explanation,
    }


def no_op(index, explanation):
    return note(index, "no_op", None, explanation, applies=False)


def hours(demand, solar, tariff):
    return [
        {"hour": h, "demand_kwh": d, "solar_kwh": s, "tariff_bdt_per_kwh": p}
        for h, (d, s, p) in enumerate(zip(demand, solar, tariff))
    ]


def battery(capacity, initial, minimum, charge, discharge):
    return {
        "capacity_kwh": capacity,
        "initial_energy_kwh": initial,
        "minimum_energy_kwh": minimum,
        "max_charge_kwh_per_hour": charge,
        "max_discharge_kwh_per_hour": discharge,
    }


CASES = [
    {
        "id": "TRICKY-01",
        "label": "Reduced TO 80% (not BY 80%) with forced solar curtailment",
        "traps": [
            "'reduced to about 80%' means factor 0.8, the inverse of SAMPLE-09's '80% reduction' -> 0.2",
            "distractor names the battery charger but imposes no constraint, so keyword matching misfires",
            "solar exceeds demand plus the charge rate at midday, so the plan must curtail rather than export",
        ],
        "operator_notes": [
            "Dust accumulation means rooftop output from 9 AM until noon will be reduced to about 80% of the forecast figure.",
            "The maintenance team finished repairing the battery charger yesterday, so it is fully available today.",
        ],
        "interpretation": [
            note(0, "solar_reduction", {"hours": [9, 10, 11], "factor": 0.8},
                 "Output is reduced to 80% of forecast, leaving 0.8 of it usable."),
            no_op(1, "A completed repair imposes no constraint on today's schedule."),
        ],
        "hours": hours(
            [70, 65, 60, 60, 65, 75, 95, 115, 135, 150, 160, 165, 170, 165, 155, 145, 140, 155, 175, 185, 175, 150, 115, 90],
            [0, 0, 0, 0, 0, 10, 40, 90, 140, 150, 170, 180, 260, 250, 220, 170, 105, 40, 5, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 6, 8, 10, 12, 14, 16, 16, 15, 14, 13, 14, 18, 22, 28, 30, 26, 18, 10, 7],
        ),
        "battery": battery(200, 100, 40, 50, 50),
        "decoy": [note(0, "solar_reduction", {"hours": [9, 10, 11], "factor": 0.2}, "decoy"), no_op(1, "d")],
        "decoy_why": "reads 'reduced to 80%' as an 80% reduction, i.e. factor 0.2"
    },
    {
        "id": "TRICKY-02",
        "label": "Midnight-crossing window with battery starting at its floor",
        "traps": [
            "'10 PM tonight until 2 AM' wraps past midnight, so hours are [0, 1, 22, 23] in ascending order, not [22, 23, 0, 1]",
            "initial_energy_kwh equals minimum_energy_kwh, so nothing can be discharged before something is charged",
            "the blocked hours 0 and 1 sit inside the cheapest tariff band",
        ],
        "operator_notes": [
            "The charging circuit is locked out from 10 PM tonight until 2 AM for switchgear work.",
        ],
        "interpretation": [
            note(0, "no_charge_window", {"hours": [0, 1, 22, 23]},
                 "The lockout spans the end of the day and wraps into the first two hours."),
        ],
        "hours": hours(
            [95, 90, 85, 85, 90, 100, 115, 135, 155, 170, 180, 185, 190, 185, 175, 170, 175, 190, 210, 220, 210, 180, 140, 110],
            [0, 0, 0, 0, 0, 0, 5, 20, 55, 95, 135, 165, 185, 175, 145, 95, 50, 10, 0, 0, 0, 0, 0, 0],
            [5, 5, 4, 4, 4, 6, 9, 12, 14, 16, 17, 17, 16, 15, 14, 15, 19, 23, 29, 31, 27, 19, 11, 7],
        ),
        "battery": battery(180, 40, 40, 45, 45),
        "decoy": [note(0, "no_charge_window", {"hours": [22, 23]}, "decoy")],
        "decoy_why": "drops the hours that wrap past midnight"
    },
    {
        "id": "TRICKY-03",
        "label": "12 PM means noon, 12 AM is a distractor",
        "traps": [
            "'12 PM until 4 PM' maps to [12, 13, 14, 15]; reading 12 PM as midnight gives a completely different window",
            "the distractor mentions 12 AM and load shedding tests but describes a cancelled event",
            "the cap binds only at hour 15 while also blocking cheap midday charging",
        ],
        "operator_notes": [
            "Grid draw must not exceed 150 kWh per hour from 12 PM until 4 PM while the substation is serviced.",
            "Note that the 12 AM load shedding tests scheduled for this week were cancelled.",
        ],
        "interpretation": [
            note(0, "max_grid_window", {"hours": [12, 13, 14, 15], "max_grid_kwh": 150},
                 "12 PM is noon, so the capped window runs from hour 12 through hour 15."),
            no_op(1, "A cancelled test imposes no constraint on today's schedule."),
        ],
        "hours": hours(
            [100, 95, 90, 90, 95, 105, 125, 145, 165, 180, 190, 200, 230, 225, 215, 210, 195, 205, 215, 225, 215, 185, 145, 115],
            [0, 0, 0, 0, 0, 0, 5, 15, 35, 55, 75, 90, 95, 90, 70, 45, 20, 5, 0, 0, 0, 0, 0, 0],
            [7, 6, 5, 5, 5, 7, 9, 12, 15, 17, 18, 18, 17, 16, 15, 16, 19, 23, 28, 31, 27, 19, 12, 8],
        ),
        "battery": battery(220, 110, 50, 55, 55),
        "decoy": [note(0, "max_grid_window", {"hours": [0, 1, 2, 3], "max_grid_kwh": 150}, "decoy"), no_op(1, "d")],
        "decoy_why": "reads 12 PM as midnight"
    },
    {
        "id": "TRICKY-04",
        "label": "Reserve phrased as a maximum draw-down",
        "traps": [
            "'do not draw below 60% of capacity' is a reserve floor of 0.6 x 250 = 150 kWh, phrased as a limit rather than a minimum",
            "the floor exceeds the starting energy, so the battery must be charged up before the window opens",
            "'between 5 PM and 9 PM' covers hours 17 through 20",
        ],
        "operator_notes": [
            "Do not draw the battery below 60% of its rated capacity between 5 PM and 9 PM.",
        ],
        "interpretation": [
            note(0, "minimum_battery_reserve", {"hours": [17, 18, 19, 20], "minimum_energy_kwh": 150},
                 "60% of the 250 kWh battery is 150 kWh, which must remain stored across the window."),
        ],
        "hours": hours(
            [105, 100, 95, 95, 100, 110, 130, 150, 170, 185, 195, 200, 205, 200, 190, 185, 195, 210, 230, 240, 230, 195, 155, 120],
            [0, 0, 0, 0, 0, 0, 5, 20, 55, 95, 135, 170, 190, 180, 150, 100, 50, 10, 0, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 7, 9, 12, 15, 17, 19, 19, 18, 16, 15, 16, 20, 24, 30, 33, 28, 20, 12, 8],
        ),
        "battery": battery(250, 120, 50, 60, 60),
        "decoy": [note(0, "minimum_battery_reserve", {"hours": [17, 18, 19, 20], "minimum_energy_kwh": 100}, "decoy")],
        "decoy_why": "treats the 40% draw-down as the floor instead of 60% remaining"
    },
    {
        "id": "TRICKY-05",
        "label": "Single-hour window with a fractional factor",
        "traps": [
            "'from 1 PM to 2 PM' is one hour, [13], not a two-hour span",
            "'one third' must become a numeric factor of about 0.3333",
            "the distractor says charging capacity was restored, naming the charger but constraining nothing",
        ],
        "operator_notes": [
            "Inverter servicing from 1 PM to 2 PM will leave only about one third of the forecast solar usable.",
            "Charging capacity was restored this morning following last week's fault.",
        ],
        "interpretation": [
            note(0, "solar_reduction", {"hours": [13], "factor": THIRD},
                 "A one-hour window keeps roughly a third of the forecast usable."),
            no_op(1, "A restored capability imposes no constraint on today's schedule."),
        ],
        "hours": hours(
            [95, 90, 85, 85, 90, 100, 120, 140, 160, 175, 185, 190, 195, 190, 180, 175, 180, 195, 215, 225, 215, 185, 145, 110],
            [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160, 175, 150, 140, 95, 45, 10, 0, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 6, 8, 11, 14, 16, 18, 18, 17, 15, 14, 15, 19, 23, 29, 31, 27, 19, 11, 7],
        ),
        "battery": battery(210, 105, 45, 50, 50),
        "decoy": [note(0, "solar_reduction", {"hours": [13, 14], "factor": THIRD}, "decoy"), no_op(1, "d")],
        "decoy_why": "treats the end of the window as inclusive"
    },
    {
        "id": "TRICKY-06",
        "label": "Window ending at midnight with asymmetric rate limits",
        "traps": [
            "'8 PM until midnight' ends at hour 24, which clips to [20, 21, 22, 23] rather than overflowing",
            "the tariff rises all evening and peaks at hour 23, so dropping that hour from the window looks harmless but is the costliest mistake available",
            "discharge is blocked across the last four hours, so end-of-day neutrality must be reached without it",
            "charge rate 30 against discharge rate 70 means energy takes more than twice as long to store as to release",
        ],
        "operator_notes": [
            "Relay testing prohibits any battery discharge from 8 PM until midnight.",
        ],
        "interpretation": [
            note(0, "no_discharge_window", {"hours": [20, 21, 22, 23]},
                 "The prohibition runs to the end of the day, covering hours 20 through 23."),
        ],
        "hours": hours(
            [100, 95, 90, 90, 95, 105, 125, 145, 165, 180, 190, 195, 200, 195, 185, 180, 190, 205, 225, 235, 225, 190, 150, 120],
            [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160, 180, 170, 140, 90, 45, 10, 0, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 7, 9, 12, 15, 17, 19, 19, 18, 16, 15, 16, 18, 20, 22, 25, 28, 30, 33, 35],
        ),
        "battery": battery(240, 120, 50, 30, 70),
        "decoy": [note(0, "no_discharge_window", {"hours": [20, 21, 22]}, "decoy")],
        "decoy_why": "stops before midnight, dropping hour 23"
    },
    {
        "id": "TRICKY-07",
        "label": "Two overlapping reserves, strictest wins per hour",
        "traps": [
            "two notes of the same directive type overlap; hours 19 and 20 must take the higher 120 kWh floor",
            "naive handling overwrites the first reserve instead of merging it, dropping the 80 kWh floor at hours 18 and 21",
            "the resulting floor profile is stepped rather than flat across the window",
        ],
        "operator_notes": [
            "Keep at least 80 kWh in the battery from 6 PM until 10 PM for the campus clinic.",
            "The data centre has separately asked that 120 kWh be held from 7 PM until 9 PM.",
        ],
        "interpretation": [
            note(0, "minimum_battery_reserve", {"hours": [18, 19, 20, 21], "minimum_energy_kwh": 80},
                 "The clinic needs 80 kWh held across the four-hour evening window."),
            note(1, "minimum_battery_reserve", {"hours": [19, 20], "minimum_energy_kwh": 120},
                 "The data centre raises the floor to 120 kWh for two of those hours."),
        ],
        "hours": hours(
            [95, 90, 85, 85, 90, 100, 120, 140, 160, 175, 185, 190, 195, 190, 180, 175, 185, 200, 220, 230, 220, 190, 150, 115],
            [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160, 180, 170, 140, 90, 45, 10, 0, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 7, 9, 12, 15, 17, 19, 19, 18, 16, 15, 16, 20, 24, 30, 33, 28, 20, 12, 8],
        ),
        "battery": battery(200, 100, 40, 50, 50),
        "decoy": [note(0, "minimum_battery_reserve", {"hours": [19, 20], "minimum_energy_kwh": 120}, "decoy")],
        "decoy_why": "overwrites the first reserve instead of merging the two"
    },
    {
        "id": "TRICKY-08",
        "label": "Flat tariff, so the battery moves for feasibility not profit",
        "traps": [
            "every hour costs the same, so arbitrage has zero gradient and cost-driven heuristics idle the battery",
            "the grid cap still forces a discharge that must be pre-charged hours earlier",
            "many schedules tie on cost, so the plan must be valid rather than merely cheap",
        ],
        "operator_notes": [
            "The feeder is derated tonight: grid import must stay at or below 165 kWh in any hour from 6 PM until 9 PM.",
        ],
        "interpretation": [
            note(0, "max_grid_window", {"hours": [18, 19, 20], "max_grid_kwh": 165},
                 "Grid import is capped at 165 kWh for each hour of the derating window."),
        ],
        "hours": hours(
            [90, 85, 80, 80, 85, 95, 110, 130, 150, 165, 175, 180, 185, 180, 170, 165, 170, 185, 200, 210, 195, 165, 130, 100],
            [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160, 180, 170, 140, 90, 45, 10, 0, 0, 0, 0, 0, 0],
            [12] * 24,
        ),
        "battery": battery(200, 90, 30, 50, 50),
        "decoy": [no_op(0, "decoy")],
        "decoy_why": "misses the directive because a flat tariff makes it look irrelevant"
    },
    {
        "id": "TRICKY-09",
        "label": "Battery starts full, solar zeroed across midday",
        "traps": [
            "initial_energy_kwh equals capacity_kwh, so hour 0 cannot charge at all",
            "factor 0.0 is falsy and is easily dropped by a truthiness check, silently restoring full solar",
            "neutrality forces the battery back to a completely full state by hour 23",
        ],
        "operator_notes": [
            "Total cloud cover is forecast, so treat rooftop solar as unavailable from 10 AM until 3 PM.",
            "The sports complex will host an inter-university tournament next month.",
        ],
        "interpretation": [
            note(0, "solar_reduction", {"hours": [10, 11, 12, 13, 14], "factor": 0.0},
                 "Unavailable solar means none of the forecast is usable in that window."),
            no_op(1, "An event next month does not affect today's schedule."),
        ],
        "hours": hours(
            [100, 95, 90, 90, 95, 105, 125, 145, 165, 180, 190, 195, 200, 195, 185, 180, 190, 205, 225, 235, 225, 190, 150, 115],
            [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160, 180, 170, 140, 90, 45, 10, 0, 0, 0, 0, 0, 0],
            [6, 6, 5, 5, 5, 7, 9, 12, 15, 17, 19, 19, 18, 16, 15, 16, 20, 24, 30, 33, 28, 20, 12, 8],
        ),
        "battery": battery(200, 200, 40, 50, 50),
        "decoy": [no_op(0, "decoy"), no_op(1, "d")],
        "decoy_why": "drops factor 0.0 as falsy, silently restoring full solar"
    },
    {
        "id": "TRICKY-10",
        "label": "Three directives binding at once in the evening peak",
        "traps": [
            "a reserve floor, a grid cap and a charge blackout interact across overlapping evening hours",
            "the charge blackout sits immediately before the reserve window, so the battery must be filled earlier than it looks",
            "satisfying any one directive greedily makes one of the other two infeasible",
        ],
        "operator_notes": [
            "Hold at least 80 kWh in the battery from 6 PM until 9 PM for critical loads.",
            "Grid import is capped at 195 kWh from 7 PM until 10 PM while the substation is constrained.",
            "Charging is unavailable from 2 PM until 5 PM during the inverter firmware update.",
        ],
        "interpretation": [
            note(0, "minimum_battery_reserve", {"hours": [18, 19, 20], "minimum_energy_kwh": 80},
                 "Critical loads require 80 kWh to stay stored across the evening window."),
            note(1, "max_grid_window", {"hours": [19, 20, 21], "max_grid_kwh": 195},
                 "Grid import is capped at 195 kWh for each hour of the substation constraint."),
            note(2, "no_charge_window", {"hours": [14, 15, 16]},
                 "Charging is unavailable while the firmware update runs."),
        ],
        "hours": hours(
            [105, 100, 95, 95, 100, 110, 130, 150, 170, 185, 195, 205, 210, 205, 195, 190, 200, 215, 235, 245, 235, 200, 160, 125],
            [0, 0, 0, 0, 0, 0, 5, 20, 55, 95, 135, 170, 190, 180, 150, 100, 50, 10, 0, 0, 0, 0, 0, 0],
            [7, 6, 5, 5, 5, 7, 10, 13, 16, 18, 20, 20, 19, 17, 16, 17, 21, 25, 31, 34, 29, 21, 13, 9],
        ),
        "battery": battery(240, 110, 50, 55, 55),
        "decoy": [note(0, "minimum_battery_reserve", {"hours": [18, 19, 20], "minimum_energy_kwh": 80}, "d"), note(1, "max_grid_window", {"hours": [19, 20, 21], "max_grid_kwh": 195}, "d"), no_op(2, "decoy")],
        "decoy_why": "misses the third directive"
    },
]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    failures = 0

    print(f"{'case':11} {'LP cost':>11} {'DP cost':>11} {'gap':>7}  {'decoy is caught how?':28}  status")
    print("-" * 92)

    for spec in CASES:
        request = {
            "scenario_id": spec["id"],
            "operator_notes": spec["operator_notes"],
            "hours": spec["hours"],
            "battery": spec["battery"],
        }
        interpretation = spec["interpretation"]
        problems = []

        schema_errs = validate_interpretation(interpretation, len(spec["operator_notes"]))
        problems += [f"interpretation schema: {e}" for e in schema_errs]

        directives = resolve(interpretation)
        solution = optimize(request, directives)
        if solution.status != "optimal":
            problems.append(f"infeasible as authored (relaxed {solution.relaxed})")

        response = build_response(request, interpretation)
        report = replay_validate(request, directives, response)
        problems += [f"replay: {v}" for v in report.violations]

        dp_cost = dp_optimal_cost(request, directives)
        gap = dp_cost - report.total_cost_bdt
        if dp_cost < report.total_cost_bdt - 0.01:
            problems.append(f"DP found a cheaper plan ({dp_cost:.2f} < {report.total_cost_bdt:.2f})")
        elif gap > 0.01:
            problems.append(f"DP disagrees by {gap:.2f} BDT")

        # Discrimination: build the plan a team would produce after the likely
        # misreading, then judge it against the true directives. If that plan
        # survives unpunished the case teaches nothing.
        decoy_plan = optimize(request, resolve(spec["decoy"])).hourly_plan
        decoy_probe = {
            "scenario_id": spec["id"],
            "hourly_plan": decoy_plan,
            "total_grid_kwh": None,
            "total_cost_bdt": None,
            "peak_grid_kwh": None,
        }
        decoy_judged = replay_validate(request, directives, decoy_probe)
        decoy_breaks = [v for v in decoy_judged.violations if v.kind != "totals"]
        decoy_penalty = decoy_cost = decoy_judged.total_cost_bdt - report.total_cost_bdt
        # A decoy is punished either by producing an invalid plan or by costing
        # more. Escaping both means the misreading is free, so the case is inert.
        if not decoy_breaks and decoy_penalty <= 0.01:
            problems.append("decoy is valid and no costlier: case does not discriminate")
        caught = (
            f"invalid plan ({len(decoy_breaks)} violations)" if decoy_breaks
            else f"valid but costs +{decoy_penalty:,.0f} BDT"
        )

        status = "ok" if not problems else "FAIL"
        if problems:
            failures += 1
        print(
            f"{spec['id']:11} {report.total_cost_bdt:11,.2f} {dp_cost:11,.2f} "
            f"{gap:7.2f}  {caught:28}  {status}"
        )
        for p in problems:
            print(f"            - {p}")

        (OUT_DIR / f"{spec['id']}.json").write_text(
            json.dumps(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "traps": spec["traps"],
                    "input": request,
                    "decoy": spec["decoy"],
                    "expected_output": response,
                    "verification": {
                        "lp_cost_bdt": round(report.total_cost_bdt, 2),
                        "dp_oracle_cost_bdt": round(dp_cost, 2),
                        "replay_violations": len(report.violations),
                        "decoy_why": spec["decoy_why"],
                        "decoy_caught_as": caught,
                    },
                },
                indent=2,
            )
            + "\n"
        )

    print("-" * 92)
    print(f"{len(CASES) - failures}/{len(CASES)} verified, written to {OUT_DIR.relative_to(ROOT)}/")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

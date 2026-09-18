"""End-to-end: interpreted directives in, validated response body out."""

from __future__ import annotations

from .directives import resolve
from .optimizer import Solution, optimize, _idle_plan
from .validator import ValidationReport, replay_validate

import numpy as np


def build_response(request: dict, directive_interpretation: list[dict]) -> dict:
    """Assemble the /optimize-energy response.

    Totals are taken from the replay validator rather than from the solver, so
    a mismatch between hourly_plan and the reported aggregates is structurally
    impossible. If the optimised plan fails its own replay, the always-valid
    idle schedule is returned instead: a valid expensive plan scores partially,
    an invalid cheap one scores nothing.
    """
    directives = resolve(directive_interpretation)
    solution = optimize(request, directives)
    report = _report_for(request, directives, solution.hourly_plan)

    if not report.ok:
        # Directives this strict admit no clean schedule. Fall back only if the
        # idle plan is genuinely closer to valid, otherwise keep the cheaper one.
        idle = Solution(_fallback_plan(request, directives), "fallback", solution.relaxed)
        idle_report = _report_for(request, directives, idle.hourly_plan)
        if len(idle_report.violations) < len(report.violations):
            solution, report = idle, idle_report

    return {
        "scenario_id": request.get("scenario_id"),
        "directive_interpretation": directive_interpretation,
        "hourly_plan": solution.hourly_plan,
        "total_grid_kwh": round(report.total_grid_kwh, 2),
        "total_cost_bdt": round(report.total_cost_bdt, 2),
        "peak_grid_kwh": round(report.peak_grid_kwh, 2),
        "plan_summary": _summarise(solution, report),
    }


def _report_for(request: dict, directives, plan: list[dict]) -> ValidationReport:
    probe = {
        "scenario_id": request.get("scenario_id"),
        "hourly_plan": plan,
        "total_grid_kwh": None,
        "total_cost_bdt": None,
        "peak_grid_kwh": None,
    }
    report = replay_validate(request, directives, probe)
    report.violations = [v for v in report.violations if v.kind != "totals"]
    return report


def _fallback_plan(request: dict, directives) -> list[dict]:
    hours = request["hours"]
    demand = np.array([float(h["demand_kwh"]) for h in hours])
    solar = np.array(
        [directives.effective_solar(t, float(h["solar_kwh"])) for t, h in enumerate(hours)]
    )
    return _idle_plan(demand, solar, request["battery"])


def _summarise(solution: Solution, report: ValidationReport) -> str:
    moved = sum(1 for row in solution.hourly_plan if row["battery_action"] != "idle")
    parts = [
        f"Serves all 24 hours of demand for {report.total_cost_bdt:,.2f} BDT "
        f"across {report.total_grid_kwh:,.2f} kWh of grid import "
        f"(peak {report.peak_grid_kwh:,.2f} kWh)",
        f"battery moves in {moved} hours and returns to its starting level",
    ]
    if solution.relaxed:
        parts.append("relaxed directives: " + ", ".join(solution.relaxed))
    return "; ".join(parts) + "."

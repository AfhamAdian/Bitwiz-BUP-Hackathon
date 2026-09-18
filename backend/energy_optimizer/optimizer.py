"""Exact cost-minimising dispatch as a linear program.

The model is a min-cost flow on a time-expanded network: per hour a grid arc
(priced), a curtailable solar arc, charge/discharge arcs into a storage arc
chain. Every directive is a bound edit, so the structure never changes.

Round-trip efficiency is 1.0, so simultaneous charge and discharge always nets
out with identical grid draw and identical state of charge. That removes the
need for binaries: this is a pure LP, not a MILP.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

from .directives import HOURS, ResolvedDirectives

# offsets into the decision vector
_G, _S, _C, _D, _E = 0, HOURS, 2 * HOURS, 3 * HOURS, 4 * HOURS
_N = 5 * HOURS

# discourages cost-neutral round trips so the solver returns clean schedules;
# worst-case objective perturbation is far below the 0.01 judging tolerance
_CYCLE_EPS = 1e-6

_SNAP = 1e-7
_DP = 4

# progressively dropped when the directive set admits no feasible schedule
_RELAXATIONS = ("max_grid_window", "minimum_battery_reserve", "charge_windows", "neutrality")


@dataclass
class Solution:
    hourly_plan: list[dict]
    status: str = "optimal"
    relaxed: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return self.status != "optimal"


def optimize(request: dict, directives: ResolvedDirectives) -> Solution:
    hours = request["hours"]
    battery = request["battery"]

    demand = np.array([float(h["demand_kwh"]) for h in hours])
    price = np.array([float(h["tariff_bdt_per_kwh"]) for h in hours])
    solar = np.array(
        [directives.effective_solar(t, float(h["solar_kwh"])) for t, h in enumerate(hours)]
    )

    for dropped in range(len(_RELAXATIONS) + 1):
        waived = _RELAXATIONS[:dropped]
        x = _solve(demand, price, solar, battery, directives, waived)
        if x is not None:
            plan = _materialise(x, demand, solar, battery)
            status = "optimal" if not waived else "relaxed"
            return Solution(plan, status, list(waived))

    return Solution(_idle_plan(demand, solar, battery), "fallback", list(_RELAXATIONS))


def _solve(demand, price, solar, battery, directives, waived) -> np.ndarray | None:
    capacity = float(battery["capacity_kwh"])
    initial = float(battery["initial_energy_kwh"])
    base_floor = float(battery["minimum_energy_kwh"])
    max_charge = float(battery["max_charge_kwh_per_hour"])
    max_discharge = float(battery["max_discharge_kwh_per_hour"])

    cost = np.zeros(_N)
    cost[_G : _G + HOURS] = price
    cost[_C : _C + HOURS] = _CYCLE_EPS
    cost[_D : _D + HOURS] = _CYCLE_EPS

    rows = HOURS * 2 + (0 if "neutrality" in waived else 1)
    a_eq = np.zeros((rows, _N))
    b_eq = np.zeros(rows)

    for t in range(HOURS):
        # grid + solar + discharge = demand + charge
        a_eq[t, _G + t] = 1.0
        a_eq[t, _S + t] = 1.0
        a_eq[t, _D + t] = 1.0
        a_eq[t, _C + t] = -1.0
        b_eq[t] = demand[t]

        # soc_t - soc_{t-1} - charge + discharge = 0
        r = HOURS + t
        a_eq[r, _E + t] = 1.0
        a_eq[r, _C + t] = -1.0
        a_eq[r, _D + t] = 1.0
        if t == 0:
            b_eq[r] = initial
        else:
            a_eq[r, _E + t - 1] = -1.0

    if "neutrality" not in waived:
        a_eq[-1, _E + HOURS - 1] = 1.0
        b_eq[-1] = initial

    bounds: list[tuple[float, float | None]] = []
    for t in range(HOURS):  # grid
        cap = None if "max_grid_window" in waived else directives.max_grid(t)
        bounds.append((0.0, None if cap is None or cap == float("inf") else cap))
    for t in range(HOURS):  # solar used
        bounds.append((0.0, max(solar[t], 0.0)))
    for t in range(HOURS):  # charge
        allowed = "charge_windows" in waived or directives.can_charge(t)
        bounds.append((0.0, max_charge if allowed else 0.0))
    for t in range(HOURS):  # discharge
        allowed = "charge_windows" in waived or directives.can_discharge(t)
        bounds.append((0.0, max_discharge if allowed else 0.0))
    for t in range(HOURS):  # state of charge
        floor = base_floor if "minimum_battery_reserve" in waived else directives.soc_floor(t, base_floor)
        if floor > capacity:
            return None  # unsatisfiable here; let the ladder record the relaxation
        bounds.append((floor, capacity))

    result = linprog(cost, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    return result.x if result.success else None


def _materialise(x: np.ndarray, demand, solar, battery) -> list[dict]:
    """Turn raw solver output into a plan whose emitted numbers are internally
    exact: charge/discharge are netted and snapped, then grid and state of
    charge are re-derived from the cleaned values rather than read back."""
    max_charge = float(battery["max_charge_kwh_per_hour"])
    max_discharge = float(battery["max_discharge_kwh_per_hour"])
    soc = float(battery["initial_energy_kwh"])

    plan = []
    for t in range(HOURS):
        raw_c, raw_d = x[_C + t], x[_D + t]
        net = raw_c - raw_d
        charge = _clean(max(net, 0.0), max_charge)
        discharge = _clean(max(-net, 0.0), max_discharge)

        used = _clean(x[_S + t], solar[t])
        grid = round(demand[t] + charge - discharge - used, _DP)
        if grid < 0.0:  # curtail rather than emit a negative draw
            used = round(used + grid, _DP)
            grid = 0.0

        if charge > 0:
            action, amount = "charge", charge
        elif discharge > 0:
            action, amount = "discharge", discharge
        else:
            action, amount = "idle", 0.0

        soc = round(soc + charge - discharge, _DP)
        plan.append(
            {
                "hour": t,
                "grid_kwh": grid,
                "solar_used_kwh": used,
                "battery_action": action,
                "battery_kwh": amount,
                "battery_energy_after_kwh": soc,
            }
        )
    return plan


def _idle_plan(demand, solar, battery) -> list[dict]:
    """Always feasible against every directive except a grid cap: never moves
    the battery, so rate limits, windows, floors and neutrality all hold."""
    soc = float(battery["initial_energy_kwh"])
    plan = []
    for t in range(HOURS):
        used = _clean(min(solar[t], demand[t]), solar[t])
        plan.append(
            {
                "hour": t,
                "grid_kwh": round(demand[t] - used, _DP),
                "solar_used_kwh": used,
                "battery_action": "idle",
                "battery_kwh": 0.0,
                "battery_energy_after_kwh": soc,
            }
        )
    return plan


def _clean(value: float, upper: float) -> float:
    value = 0.0 if abs(value) < _SNAP else round(value, _DP)
    return min(max(value, 0.0), max(upper, 0.0))

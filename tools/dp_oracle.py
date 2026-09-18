"""Independent optimality oracle: dynamic programming over a discretised SoC grid.

Shares no code path with the LP. If DP and LP agree on cost, two unrelated
algorithms found the same optimum, which is real cross-validation rather than
the optimizer confirming itself.

DP searches a strict subset of the feasible region (SoC pinned to the grid), so
dp_cost >= lp_cost always holds. Equality confirms the LP optimum; dp_cost
strictly below lp_cost would mean the LP is over-constrained or wrong.
"""

from __future__ import annotations

import numpy as np

INF = float("inf")
EPS = 1e-9


def dp_optimal_cost(request: dict, directives, step: float = 0.25) -> float:
    hours = request["hours"]
    battery = request["battery"]

    capacity = float(battery["capacity_kwh"])
    initial = float(battery["initial_energy_kwh"])
    base_floor = float(battery["minimum_energy_kwh"])
    max_charge = float(battery["max_charge_kwh_per_hour"])
    max_discharge = float(battery["max_discharge_kwh_per_hour"])

    n = int(round(capacity / step)) + 1
    soc = np.arange(n) * step
    start = int(round(initial / step))
    if abs(start * step - initial) > EPS:
        raise ValueError(f"initial_energy_kwh {initial} is off the {step} kWh grid")

    up = int(round(max_charge / step))
    down = int(round(max_discharge / step))

    dp = np.full(n, INF)
    dp[start] = 0.0

    for t, spec in enumerate(hours):
        demand = float(spec["demand_kwh"])
        tariff = float(spec["tariff_bdt_per_kwh"])
        solar = directives.effective_solar(t, float(spec["solar_kwh"]))
        grid_cap = directives.max_grid(t)

        nxt = np.full(n, INF)
        for delta in range(-down, up + 1):
            if delta > 0 and not directives.can_charge(t):
                continue
            if delta < 0 and not directives.can_discharge(t):
                continue

            charge = delta * step if delta > 0 else 0.0
            discharge = -delta * step if delta < 0 else 0.0

            net = demand + charge - discharge
            if net < -EPS:
                continue  # would require exporting to the grid
            used = min(solar, net)
            grid = net - used
            if grid > grid_cap + EPS:
                continue

            cost = grid * tariff
            if delta >= 0:
                np.minimum(nxt[delta:], dp[: n - delta] + cost, out=nxt[delta:])
            else:
                k = -delta
                np.minimum(nxt[: n - k], dp[k:] + cost, out=nxt[: n - k])

        floor = directives.soc_floor(t, base_floor)
        nxt[soc < floor - EPS] = INF
        dp = nxt

    return float(dp[start])

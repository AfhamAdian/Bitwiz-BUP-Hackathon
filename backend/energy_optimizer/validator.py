"""Replay validator: an independent re-simulation of an hourly_plan.

Shares no code with the optimizer, so a bug in one cannot hide inside the other.
Everything is derived from the plan itself; reported values are only ever
compared against, never trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .directives import HOURS, ResolvedDirectives

TOLERANCE = 0.01

BATTERY_ACTIONS = frozenset({"charge", "discharge", "idle"})


@dataclass(frozen=True)
class Violation:
    hour: int | None
    kind: str
    detail: str

    def __str__(self) -> str:
        where = f"h{self.hour}" if self.hour is not None else "plan"
        return f"{where} [{self.kind}] {self.detail}"


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)
    total_grid_kwh: float = 0.0
    total_cost_bdt: float = 0.0
    peak_grid_kwh: float = 0.0
    final_soc: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.violations

    def __str__(self) -> str:
        if self.ok:
            return "valid"
        return "\n".join(str(v) for v in self.violations)


def replay_validate(
    request: dict,
    directives: ResolvedDirectives,
    response: dict,
    tolerance: float = TOLERANCE,
) -> ValidationReport:
    report = ValidationReport()
    add = lambda h, k, d: report.violations.append(Violation(h, k, d))

    hours_in = request.get("hours") or []
    battery = request.get("battery") or {}
    plan = response.get("hourly_plan")

    if not isinstance(plan, list) or len(plan) != HOURS:
        add(None, "schema", f"hourly_plan must hold {HOURS} entries, got {_size(plan)}")
        return report
    if len(hours_in) != HOURS:
        add(None, "schema", f"request hours must hold {HOURS} entries, got {len(hours_in)}")
        return report

    if response.get("scenario_id") != request.get("scenario_id"):
        add(None, "schema", "scenario_id does not echo the request")

    capacity = float(battery["capacity_kwh"])
    initial = float(battery["initial_energy_kwh"])
    base_floor = float(battery["minimum_energy_kwh"])
    max_charge = float(battery["max_charge_kwh_per_hour"])
    max_discharge = float(battery["max_discharge_kwh_per_hour"])

    soc = initial
    grid_series: list[float] = []
    cost = 0.0

    for t, (spec, row) in enumerate(zip(hours_in, plan)):
        if not isinstance(row, dict):
            add(t, "schema", "plan entry is not an object")
            return report
        if row.get("hour") != t:
            add(t, "schema", f"hour field is {row.get('hour')!r}, expected {t}")

        try:
            grid = float(row["grid_kwh"])
            solar_used = float(row["solar_used_kwh"])
            amount = float(row["battery_kwh"])
        except (KeyError, TypeError, ValueError):
            add(t, "schema", "missing or non-numeric plan fields")
            return report

        action = row.get("battery_action")
        if action not in BATTERY_ACTIONS:
            add(t, "schema", f"battery_action {action!r} is not a supported enum value")
            action = "idle"
            amount = 0.0

        charge = amount if action == "charge" else 0.0
        discharge = amount if action == "discharge" else 0.0

        # idle must be exactly zero, not merely close to it
        if action == "idle" and amount != 0:
            add(t, "action_consistency", f"idle with battery_kwh={amount!r}")
        if amount < -tolerance:
            add(t, "negative_value", f"battery_kwh={amount}")
        if grid < -tolerance:
            add(t, "negative_value", f"grid_kwh={grid}")
        if solar_used < -tolerance:
            add(t, "negative_value", f"solar_used_kwh={solar_used}")

        if charge > max_charge + tolerance:
            add(t, "charge_rate", f"{charge} exceeds {max_charge} per hour")
        if discharge > max_discharge + tolerance:
            add(t, "discharge_rate", f"{discharge} exceeds {max_discharge} per hour")

        if charge > tolerance and not directives.can_charge(t):
            add(t, "no_charge_window", f"charged {charge} inside a no-charge hour")
        if discharge > tolerance and not directives.can_discharge(t):
            add(t, "no_discharge_window", f"discharged {discharge} inside a no-discharge hour")

        cap = directives.max_grid(t)
        if grid > cap + tolerance:
            add(t, "max_grid_window", f"grid {grid} exceeds cap {cap}")

        available = directives.effective_solar(t, float(spec["solar_kwh"]))
        if solar_used > available + tolerance:
            add(t, "solar_overuse", f"used {solar_used} of {available} effective")

        demand = float(spec["demand_kwh"])
        supply = grid + solar_used + discharge
        draw = demand + charge
        if abs(supply - draw) > tolerance:
            add(t, "energy_balance", f"{supply:.4f} != {draw:.4f}")

        # replay the battery forward; the reported value is only a claim
        soc += charge - discharge
        claimed = row.get("battery_energy_after_kwh")
        if not isinstance(claimed, (int, float)) or isinstance(claimed, bool):
            add(t, "schema", "battery_energy_after_kwh is not numeric")
        elif abs(float(claimed) - soc) > tolerance:
            add(t, "soc_drift", f"claimed {claimed}, replay gives {soc:.4f}")

        floor = directives.soc_floor(t, base_floor)
        if soc < floor - tolerance:
            add(t, "soc_below_floor", f"{soc:.4f} below {floor}")
        if soc > capacity + tolerance:
            add(t, "soc_above_capacity", f"{soc:.4f} above {capacity}")

        grid_series.append(grid)
        cost += grid * float(spec["tariff_bdt_per_kwh"])

    if abs(soc - initial) > tolerance:
        add(None, "neutrality", f"final SoC {soc:.4f} != initial {initial}")

    report.final_soc = soc
    report.total_grid_kwh = sum(grid_series)
    report.total_cost_bdt = cost
    report.peak_grid_kwh = max(grid_series)

    for name, actual in (
        ("total_grid_kwh", report.total_grid_kwh),
        ("total_cost_bdt", report.total_cost_bdt),
        ("peak_grid_kwh", report.peak_grid_kwh),
    ):
        claimed = response.get(name)
        if not isinstance(claimed, (int, float)) or isinstance(claimed, bool):
            add(None, "totals", f"{name} is missing or non-numeric")
        elif abs(float(claimed) - actual) > tolerance:
            add(None, "totals", f"{name} claimed {claimed}, recomputed {actual:.4f}")

    return report


def _size(value) -> str:
    try:
        return str(len(value))
    except TypeError:
        return type(value).__name__

"""Wire-format directive_interpretation -> per-hour overlay consumed by the
optimizer and the validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf, isfinite

HOURS = 24

DIRECTIVE_TYPES = frozenset(
    {
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    }
)

# structured_adjustment payload key carrying the directive's numeric value
VALUE_KEY = {
    "solar_reduction": "factor",
    "minimum_battery_reserve": "minimum_energy_kwh",
    "max_grid_window": "max_grid_kwh",
    "no_charge_window": None,
    "no_discharge_window": None,
}


@dataclass
class ResolvedDirectives:
    solar_factor: dict[int, float] = field(default_factory=dict)
    reserve: dict[int, float] = field(default_factory=dict)
    grid_cap: dict[int, float] = field(default_factory=dict)
    no_charge: set[int] = field(default_factory=set)
    no_discharge: set[int] = field(default_factory=set)

    def effective_solar(self, hour: int, forecast: float) -> float:
        return forecast * self.solar_factor.get(hour, 1.0)

    def soc_floor(self, hour: int, base_minimum: float) -> float:
        return max(base_minimum, self.reserve.get(hour, 0.0))

    def max_grid(self, hour: int) -> float:
        return self.grid_cap.get(hour, inf)

    def can_charge(self, hour: int) -> bool:
        return hour not in self.no_charge

    def can_discharge(self, hour: int) -> bool:
        return hour not in self.no_discharge


def resolve(directive_interpretation: list[dict]) -> ResolvedDirectives:
    """Flatten per-note directives into per-hour lookups.

    Overlapping directives of the same type collapse to the strictest value, so
    a malformed duplicate can only ever tighten the feasible region.
    """
    out = ResolvedDirectives()

    for entry in directive_interpretation or []:
        if not isinstance(entry, dict):
            continue
        if not entry.get("applies"):
            continue
        dtype = entry.get("directive_type")
        adj = entry.get("structured_adjustment")
        if dtype == "no_op" or dtype not in DIRECTIVE_TYPES or not isinstance(adj, dict):
            continue

        hours = [h for h in adj.get("hours", []) if isinstance(h, int) and 0 <= h < HOURS]
        if not hours:
            continue

        if dtype == "solar_reduction":
            factor = _as_float(adj.get("factor"))
            if factor is None:
                continue
            factor = min(max(factor, 0.0), 1.0)
            for h in hours:
                out.solar_factor[h] = min(out.solar_factor.get(h, 1.0), factor)

        elif dtype == "minimum_battery_reserve":
            value = _as_float(adj.get("minimum_energy_kwh"))
            if value is None:
                continue
            for h in hours:
                out.reserve[h] = max(out.reserve.get(h, 0.0), value)

        elif dtype == "max_grid_window":
            value = _as_float(adj.get("max_grid_kwh"))
            if value is None:
                continue
            for h in hours:
                out.grid_cap[h] = min(out.grid_cap.get(h, inf), value)

        elif dtype == "no_charge_window":
            out.no_charge.update(hours)

        elif dtype == "no_discharge_window":
            out.no_discharge.update(hours)

    return out


def validate_interpretation(
    directive_interpretation: list[dict], note_count: int
) -> list[str]:
    """Schema checks on the wire format, independent of any schedule."""
    errs: list[str] = []

    if not isinstance(directive_interpretation, list):
        return ["directive_interpretation: not a list"]
    if len(directive_interpretation) != note_count:
        errs.append(
            f"directive_interpretation: {len(directive_interpretation)} entries "
            f"for {note_count} operator notes"
        )

    for i, entry in enumerate(directive_interpretation):
        if not isinstance(entry, dict):
            errs.append(f"entry {i}: not an object")
            continue

        if entry.get("note_index") != i:
            errs.append(f"entry {i}: note_index={entry.get('note_index')}, expected {i}")

        dtype = entry.get("directive_type")
        applies = entry.get("applies")
        adj = entry.get("structured_adjustment")

        if dtype not in DIRECTIVE_TYPES:
            errs.append(f"entry {i}: unsupported directive_type {dtype!r}")
            continue

        if not isinstance(entry.get("explanation"), str) or not entry["explanation"]:
            errs.append(f"entry {i}: missing explanation")

        if dtype == "no_op":
            if applies is not False:
                errs.append(f"entry {i}: no_op must set applies=false")
            if adj is not None:
                errs.append(f"entry {i}: no_op must set structured_adjustment=null")
            continue

        if applies is not True:
            errs.append(f"entry {i}: {dtype} must set applies=true")
        if not isinstance(adj, dict):
            errs.append(f"entry {i}: {dtype} needs a structured_adjustment object")
            continue

        errs.extend(f"entry {i}: {e}" for e in _check_hours(adj.get("hours")))

        key = VALUE_KEY[dtype]
        if key is not None:
            value = _as_float(adj.get(key))
            if value is None:
                errs.append(f"entry {i}: {dtype} missing numeric {key}")
            elif dtype == "solar_reduction" and not 0.0 <= value <= 1.0:
                errs.append(f"entry {i}: factor {value} outside [0, 1]")
            elif dtype != "solar_reduction" and value < 0:
                errs.append(f"entry {i}: {key} is negative")

    return errs


def _check_hours(hours) -> list[str]:
    if not isinstance(hours, list) or not hours:
        return ["hours must be a non-empty list"]
    errs = []
    if any(not isinstance(h, int) or isinstance(h, bool) for h in hours):
        errs.append("hours must be integers")
        return errs
    if any(not 0 <= h < HOURS for h in hours):
        errs.append("hours must fall in 0..23")
    if len(set(hours)) != len(hours):
        errs.append("hours must be unique")
    if hours != sorted(hours):
        errs.append("hours must be ascending")
    return errs


def _as_float(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if isfinite(value) else None

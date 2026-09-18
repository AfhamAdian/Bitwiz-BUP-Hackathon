from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]


class DirectiveInterpretation(BaseModel):
    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict[str, Any] | None = None
    explanation: str


def _strict_int(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("must be an integer, not a string, bool, or float")
    return value


def _strict_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number, not a string or bool")
    return value


class HourRow(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)

    _check_hour = field_validator("hour", mode="before")(_strict_int)
    _check_numeric = field_validator(
        "demand_kwh", "solar_kwh", "tariff_bdt_per_kwh", mode="before"
    )(_strict_number)


class Battery(BaseModel):
    capacity_kwh: float = Field(ge=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)

    _check_numeric = field_validator(
        "capacity_kwh",
        "initial_energy_kwh",
        "minimum_energy_kwh",
        "max_charge_kwh_per_hour",
        "max_discharge_kwh_per_hour",
        mode="before",
    )(_strict_number)

    @model_validator(mode="after")
    def _check_consistency(self) -> "Battery":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be below minimum_energy_kwh")
        return self


class ParseNotesRequest(BaseModel):
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    battery: Battery | None = None
    hours: list[HourRow] | None = None


class ParseNotesResponse(BaseModel):
    directive_interpretation: list[DirectiveInterpretation]


class OptimizeRequest(BaseModel):
    scenario_id: str
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourRow] = Field(min_length=24, max_length=24)
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def _check_notes_nonblank(cls, notes: list[str]) -> list[str]:
        if any(not note.strip() for note in notes):
            raise ValueError("operator_notes entries must be non-empty and non-whitespace")
        return notes

    @model_validator(mode="after")
    def _check_hours_cover_the_day(self) -> "OptimizeRequest":
        hours = {row.hour for row in self.hours}
        if hours != set(range(24)):
            raise ValueError("hours must contain exactly one entry for each hour 0-23")
        return self


class HourlyPlanRow(BaseModel):
    hour: int = Field(ge=0, le=23)
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    scenario_id: str | None
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanRow]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str

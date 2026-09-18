from typing import Any, Literal

from pydantic import BaseModel, Field

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


class HourRow(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class Battery(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


class ParseNotesRequest(BaseModel):
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    battery: Battery | None = None
    hours: list[HourRow] | None = None


class ParseNotesResponse(BaseModel):
    directive_interpretation: list[DirectiveInterpretation]

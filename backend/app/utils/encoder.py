HOUR_COLUMNS = ("hour", "demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")


def _num(value: float) -> str:
    return f"{value:g}"


def encode_notes(operator_notes: list[str]) -> str:
    rows = "\n".join(f"[{index}] {note}" for index, note in enumerate(operator_notes))
    return f"operator_notes:\n{rows}"


def encode_hours(hours: list[dict]) -> str:
    rows = [
        "|".join(_num(row[column]) for column in HOUR_COLUMNS)
        for row in sorted(hours, key=lambda row: row["hour"])
    ]
    return "\n".join(["|".join(HOUR_COLUMNS), *rows])


def encode_battery(battery: dict) -> str:
    return "battery: " + " ".join(f"{key}={_num(value)}" for key, value in battery.items())


def encode_request(
    operator_notes: list[str], battery: dict | None = None, hours: list[dict] | None = None
) -> str:
    blocks = [encode_notes(operator_notes)]
    if hours:
        blocks.append(encode_hours(hours))
    if battery:
        blocks.append(encode_battery(battery))
    return "\n\n".join(blocks)

import logging

from app.schemas import DirectiveInterpretation, OptimizeRequest
from app.utils import gridwise_bridge  # noqa: F401  (sys.path bootstrap, keep first)
from app.utils.encoder import encode_request
from app.utils.llm import generate_json

from gridwise.directives import validate_interpretation
from gridwise.pipeline import build_response

logger = logging.getLogger(__name__)

NO_OP_EXPLANATION = "This note does not affect today's 24-hour energy schedule."

# directive_type -> (numeric field name, coercion) for fields beyond "hours".
_NUMERIC_FIELD = {
    "solar_reduction": "factor",
    "minimum_battery_reserve": "minimum_energy_kwh",
    "max_grid_window": "max_grid_kwh",
    "no_charge_window": None,
    "no_discharge_window": None,
}

SYSTEM_PROMPT = """You convert campus operator notes into structured directives for a 24-hour
campus electricity schedule. Interpret every note literally and return machine-checkable JSON.

SUPPORTED DIRECTIVES (no others exist)
- solar_reduction        {"hours": [int], "factor": number}
- minimum_battery_reserve {"hours": [int], "minimum_energy_kwh": number}
- no_charge_window       {"hours": [int]}
- no_discharge_window    {"hours": [int]}
- max_grid_window        {"hours": [int], "max_grid_kwh": number}
- no_op                  structured_adjustment is null

TIME WINDOWS
Hours are integers 0-23, unique and ascending. The start hour is INCLUDED, the end hour is
EXCLUDED, so a window that runs "from A until B" covers B - A hours:
- "from noon until 2 PM"      -> [12, 13]
- "from 2 AM until 5 AM"      -> [2, 3, 4]
- "from 6 PM until 9 PM"      -> [18, 19, 20]
- "from 6 PM until 10 PM"     -> [18, 19, 20, 21]
- "between 11 AM and 2 PM"    -> [11, 12, 13]

SOLAR FACTOR
factor is the fraction of forecast solar that REMAINS usable, never the amount lost:
- "treated as roughly 25% of the forecast" -> 0.25
- "about half of the forecast output"      -> 0.5
- "an 80% reduction in solar"              -> 0.2   (100% - 80% remains)

BATTERY RESERVE
minimum_energy_kwh is an absolute kWh value. When the note gives a percentage or fraction of the
battery, convert it with capacity_kwh from the battery object in the input:
- "at least 50% of the battery capacity", capacity_kwh 200 -> 100
- "half the battery in reserve", capacity_kwh 240          -> 120
- "at least 90 kWh"                                        -> 90
Never return no_op merely because a number must be calculated. Do the arithmetic.

SCENARIO DATA
The scenario arrives as a pipe-delimited table, one row per hour, with the header
hour|demand_kwh|solar_kwh|tariff_bdt_per_kwh, followed by a battery line. Use it only to resolve
references a note makes to the scenario, such as "the most expensive hours", "the solar peak", or
a limit stated as a share of demand. The data is never itself a reason to create a directive: if a
note states no constraint, it stays no_op no matter what the numbers look like.

WHEN TO USE no_op
Only for notes that genuinely do not change today's electricity schedule, such as deadlines,
menus, room bookings, or announcements. no_op is the only directive allowed to have
applies=false; every other directive must have applies=true.

HARD RULES
- Return exactly one entry per note, in note_index order starting at 0.
- Never invent demand, solar, tariff, or battery values that are not in the input.
- Use only the directive types listed above.
- explanation is one short sentence; state the arithmetic when you converted a percentage.

Respond with JSON only:
{"directive_interpretation": [{"note_index": 0, "applies": true, "directive_type": "...",
"structured_adjustment": {...} or null, "explanation": "..."}]}"""


async def parse_op_notes(
    operator_notes: list[str],
    battery: dict | None = None,
    hours: list[dict] | None = None,
) -> list[DirectiveInterpretation]:
    logger.info(
        "[notes] parsing %d note(s) | battery capacity=%s | hours=%s",
        len(operator_notes),
        battery.get("capacity_kwh") if battery else "not provided",
        len(hours) if hours else "not provided",
    )
    user_prompt = encode_request(operator_notes, battery, hours)
    raw = await generate_json(SYSTEM_PROMPT, user_prompt)
    entries = _normalize(raw, len(operator_notes))
    logger.info(
        "[notes] interpreted -> %s",
        ", ".join(f"{e.note_index}:{e.directive_type}" for e in entries),
    )
    return entries


def _normalize(raw: object, note_count: int) -> list[DirectiveInterpretation]:
    entries = raw.get("directive_interpretation") if isinstance(raw, dict) else raw
    by_index = {}
    if isinstance(entries, list):
        for position, item in enumerate(entries):
            if isinstance(item, dict):
                index = item.get("note_index")
                by_index[index if isinstance(index, int) else position] = item
    return [_normalize_entry(by_index.get(i), i) for i in range(note_count)]


def _normalize_entry(item: dict | None, note_index: int) -> DirectiveInterpretation:
    item = item or {}
    directive_type = item.get("directive_type")
    adjustment = _clean_adjustment(directive_type, item.get("structured_adjustment"))
    explanation = str(item.get("explanation") or "").strip()

    if adjustment is None:
        if directive_type not in (None, "no_op"):
            logger.warning(
                "[guardrail] note %d: rejected directive_type=%s adjustment=%s -> no_op",
                note_index, directive_type, item.get("structured_adjustment"),
            )
        return DirectiveInterpretation(
            note_index=note_index,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation=explanation if directive_type == "no_op" else NO_OP_EXPLANATION,
        )

    return DirectiveInterpretation(
        note_index=note_index,
        applies=True,
        directive_type=directive_type,
        structured_adjustment=adjustment,
        explanation=explanation or f"Applied {directive_type} for hours {adjustment['hours']}.",
    )


def _clean_adjustment(directive_type: object, adjustment: object) -> dict | None:
    """Return a spec-valid structured_adjustment, or None to force a no_op entry."""
    if directive_type not in _NUMERIC_FIELD or not isinstance(adjustment, dict):
        return None

    hours = _clean_hours(adjustment.get("hours"))
    if not hours:
        return None

    cleaned = {"hours": hours}
    field = _NUMERIC_FIELD[directive_type]
    if field is None:
        return cleaned

    value = adjustment.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if directive_type == "solar_reduction" and not 0 <= value <= 1:
        return None

    cleaned[field] = value
    return cleaned


def _clean_hours(hours: object) -> list[int]:
    if not isinstance(hours, list):
        return []
    valid = {h for h in hours if isinstance(h, int) and not isinstance(h, bool) and 0 <= h <= 23}
    return sorted(valid)


def _all_no_op(note_count: int) -> list[dict]:
    return [
        {
            "note_index": i,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": NO_OP_EXPLANATION,
        }
        for i in range(note_count)
    ]


async def run_optimize(payload: OptimizeRequest) -> dict:
    """POST /optimize-energy: LLM interpretation -> guardrails -> gridwise optimizer."""
    request = payload.model_dump()
    request["hours"] = sorted(request["hours"], key=lambda row: row["hour"])

    interpretations = await parse_op_notes(
        payload.operator_notes, request["battery"], request["hours"]
    )
    directive_interpretation = [entry.model_dump() for entry in interpretations]

    errors = validate_interpretation(directive_interpretation, len(payload.operator_notes))
    if errors:
        # _normalize already guarantees spec-valid entries; this is a last-resort
        # net against a shape neither of us anticipated. Never crash, never
        # invent a directive -> fall back to the always-safe no_op interpretation.
        logger.error("[guardrail] directive_interpretation failed validation: %s", errors)
        directive_interpretation = _all_no_op(len(payload.operator_notes))

    return build_response(request, directive_interpretation)

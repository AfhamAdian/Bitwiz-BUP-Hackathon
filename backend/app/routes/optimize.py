import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.services.optimize_service import OptimizeService
from app.utils.directive_validation import InterpretationError, strict_json
from app.utils.input_validation import validate_input

router = APIRouter(prefix="/optimize-energy", tags=["optimize"])

# Documentation only (see docstring below for why this endpoint reads the raw
# body instead of a Pydantic model). Keeps /docs "Try it out" usable.
_REQUEST_BODY_EXAMPLE = {
    "scenario_id": "SAMPLE-01",
    "operator_notes": [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "The cafeteria menu changes tomorrow.",
    ],
    "hours": [
        {"hour": h, "demand_kwh": 150, "solar_kwh": 0, "tariff_bdt_per_kwh": 10}
        for h in range(24)
    ],
    "battery": {
        "capacity_kwh": 220,
        "initial_energy_kwh": 110,
        "minimum_energy_kwh": 40,
        "max_charge_kwh_per_hour": 50,
        "max_discharge_kwh_per_hour": 50,
    },
}

_REQUEST_BODY_SCHEMA = {
    "type": "object",
    "required": ["scenario_id", "operator_notes", "hours", "battery"],
    "properties": {
        "scenario_id": {"type": "string"},
        "operator_notes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "hours": {
            "type": "array",
            "minItems": 24,
            "maxItems": 24,
            "items": {
                "type": "object",
                "required": ["hour", "demand_kwh", "solar_kwh", "tariff_bdt_per_kwh"],
                "properties": {
                    "hour": {"type": "integer", "minimum": 0, "maximum": 23},
                    "demand_kwh": {"type": "number", "minimum": 0},
                    "solar_kwh": {"type": "number", "minimum": 0},
                    "tariff_bdt_per_kwh": {"type": "number", "minimum": 0},
                },
            },
        },
        "battery": {
            "type": "object",
            "required": [
                "capacity_kwh",
                "initial_energy_kwh",
                "minimum_energy_kwh",
                "max_charge_kwh_per_hour",
                "max_discharge_kwh_per_hour",
            ],
            "properties": {
                "capacity_kwh": {"type": "number", "minimum": 0},
                "initial_energy_kwh": {"type": "number", "minimum": 0},
                "minimum_energy_kwh": {"type": "number", "minimum": 0},
                "max_charge_kwh_per_hour": {"type": "number", "minimum": 0},
                "max_discharge_kwh_per_hour": {"type": "number", "minimum": 0},
            },
        },
    },
}


def get_service():
    return OptimizeService()


@router.post(
    "",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _REQUEST_BODY_SCHEMA,
                    "example": _REQUEST_BODY_EXAMPLE,
                }
            },
        }
    },
)
@router.post("/", include_in_schema=False)
async def optimize(request: Request, service: OptimizeService = Depends(get_service)):
    """Reads the raw body (not a Pydantic model) so `strict_json` can reject
    duplicate keys and non-finite numbers that default JSON parsing would
    silently accept. The `openapi_extra` above only documents the shape for
    /docs "Try it out" — it does not change how the body is parsed."""
    try:
        payload = strict_json(await request.body())
        validate_input(payload)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return JSONResponse(status_code=400, content={'error': {'code': 'INVALID_REQUEST', 'message': 'Request must match the GridWise scenario schema.'}})
    try:
        result = await asyncio.wait_for(service.run(payload), timeout=28.0)
        return JSONResponse(result)
    except InterpretationError as exc:
        return JSONResponse(status_code=500, content={'error': {
            'code': 'INTERPRETATION_FAILED',
            'message': 'Operator notes could not be validated after bounded retries.',
            'issues': exc.issues,
        }})
    except TimeoutError:
        return JSONResponse(status_code=500, content={'error': {'code': 'PROCESSING_TIMEOUT', 'message': 'Processing exceeded the time budget.'}})
    except ValueError:
        return JSONResponse(status_code=500, content={'error': {'code': 'PLAN_UNAVAILABLE', 'message': 'A validated feasible plan could not be produced.'}})
    except Exception:
        # Never expose raw provider responses, request data, secrets or tracebacks.
        return JSONResponse(status_code=500, content={'error': {'code': 'INTERNAL_ERROR', 'message': 'Unable to complete this request.'}})

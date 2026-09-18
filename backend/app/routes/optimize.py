import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.services.optimize_service import OptimizeService
from app.utils.directive_validation import InterpretationError, strict_json
from app.utils.input_validation import validate_input

router = APIRouter(prefix="/optimize-energy", tags=["optimize"])


def get_service():
    return OptimizeService()


@router.post("")
@router.post("/", include_in_schema=False)
async def optimize(request: Request, service: OptimizeService = Depends(get_service)):
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

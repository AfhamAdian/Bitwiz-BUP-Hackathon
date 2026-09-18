from fastapi import APIRouter

from app.schemas import OptimizeRequest, OptimizeResponse
from app.services.optimize_service import run_optimize

router = APIRouter(prefix="/optimize-energy", tags=["optimize"])


@router.post("", response_model=OptimizeResponse)
async def optimize(payload: OptimizeRequest) -> OptimizeResponse:
    return OptimizeResponse.model_validate(await run_optimize(payload))

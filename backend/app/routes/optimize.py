from fastapi import APIRouter

router = APIRouter(prefix="/optimize-energy", tags=["optimize"])


@router.post("/")
async def optimize():
    return {"status": "ok"}

from fastapi import APIRouter

router = APIRouter(prefix="/optimize", tags=["optimize"])


@router.post("/")
async def optimize():
    return {"status": "ok"}

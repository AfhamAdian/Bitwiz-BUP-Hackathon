from fastapi import APIRouter

from app.schemas import ParseNotesRequest, ParseNotesResponse
from app.services.optimize_service import parse_op_notes

router = APIRouter(prefix="/test", tags=["test"])


@router.post("")
async def test_parse_op_notes(payload: ParseNotesRequest) -> ParseNotesResponse:
    battery = payload.battery.model_dump() if payload.battery else None
    hours = [row.model_dump() for row in payload.hours] if payload.hours else None
    return ParseNotesResponse(
        directive_interpretation=await parse_op_notes(payload.operator_notes, battery, hours)
    )

from uuid import UUID

from fastapi import APIRouter, Request

from packages.contracts.response import TurnResponse
from packages.contracts.turn import TurnRequest

router = APIRouter(prefix='/api/sessions')


@router.post('/{session_id}/turns', response_model=TurnResponse)
async def submit_turn(session_id: UUID, body: TurnRequest, request: Request):
    return await request.app.state.orchestrator.submit_turn(str(session_id), body.participant_text, body.input_mode)

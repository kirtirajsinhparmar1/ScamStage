from uuid import UUID

from fastapi import APIRouter, Request

from packages.contracts.response import SessionDetail, SessionResponse
from packages.contracts.session import SessionRequest

router = APIRouter(prefix='/api/sessions')


@router.post('', response_model=SessionResponse)
async def create_session(request: Request, body: SessionRequest | None = None):
    return await request.app.state.orchestrator.create_session((body or SessionRequest()).scenario_id)


@router.get('/{session_id}', response_model=SessionDetail)
async def get_session(session_id: UUID, request: Request):
    return request.app.state.orchestrator.get_session(str(session_id))

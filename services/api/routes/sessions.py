from uuid import UUID

from fastapi import APIRouter, Request

from packages.contracts.evaluation import EvaluationResponse
from packages.contracts.response import EndCallResponse, SessionDetail, SessionResponse, TurnResponse
from packages.contracts.session import SessionRequest

router = APIRouter(prefix='/api/sessions')


@router.post('', response_model=SessionResponse)
async def create_session(request: Request, body: SessionRequest | None = None):
    body = body or SessionRequest()
    return await request.app.state.orchestrator.create_session(body.scenario_id, body.interaction_mode)


@router.get('/{session_id}/evaluation', response_model=EvaluationResponse)
async def get_evaluation(session_id: UUID, request: Request):
    return request.app.state.orchestrator.get_evaluation(str(session_id))


@router.post('/{session_id}/end', response_model=EndCallResponse)
async def end_call(session_id: UUID, request: Request):
    return await request.app.state.orchestrator.end_call(str(session_id))


@router.post('/{session_id}/dialogue/retry', response_model=SessionResponse | TurnResponse)
async def retry_dialogue(session_id: UUID, request: Request):
    return await request.app.state.orchestrator.retry_dialogue(str(session_id))


@router.get('/{session_id}', response_model=SessionDetail)
async def get_session(session_id: UUID, request: Request):
    return request.app.state.orchestrator.get_session(str(session_id))

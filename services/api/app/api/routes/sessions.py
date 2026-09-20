from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_session_repo
from app.database.memory import InMemorySessionRepository
from app.schemas.contracts import SessionResponse

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(
    repo: InMemorySessionRepository = Depends(get_session_repo),
) -> SessionResponse:
    return repo.create_session()


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
def end_session(
    session_id: str,
    repo: InMemorySessionRepository = Depends(get_session_repo),
) -> SessionResponse:
    session = repo.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

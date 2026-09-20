import uuid
from typing import Dict, Optional

from app.domain.enums import ScenarioState
from app.schemas.contracts import SessionResponse


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionResponse] = {}

    def create_session(self) -> SessionResponse:
        session_id = str(uuid.uuid4())
        session = SessionResponse(
            id=session_id,
            status="active",
            scenario_state=ScenarioState.INTRO,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionResponse]:
        return self._sessions.get(session_id)

    def end_session(self, session_id: str) -> Optional[SessionResponse]:
        session = self.get_session(session_id)
        if session:
            # End the session and update the scenario state
            new_session = SessionResponse(
                id=session.id,
                status="ended",
                scenario_state=ScenarioState.COMPLETED,
            )
            self._sessions[session_id] = new_session
            return new_session
        return None

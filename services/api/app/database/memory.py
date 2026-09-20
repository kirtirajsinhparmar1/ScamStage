import uuid
from typing import Any, Dict, List, Literal, Optional

from app.domain.enums import ScenarioState
from app.schemas.contracts import SessionResponse


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionResponse] = {}
        self._turns: Dict[str, List[Dict[str, Any]]] = {}

    def create_session(self) -> SessionResponse:
        session_id = str(uuid.uuid4())
        session = SessionResponse(
            id=session_id,
            status="active",
            scenario_state=ScenarioState.INTRO,
        )
        self._sessions[session_id] = session
        self._turns[session_id] = []
        return session

    def get_session(self, session_id: str) -> Optional[SessionResponse]:
        return self._sessions.get(session_id)

    def update_session(
        self,
        session_id: str,
        scenario_state: ScenarioState,
        status: Literal["active", "ended"] = "active",
    ) -> Optional[SessionResponse]:
        session = self.get_session(session_id)
        if session:
            updated = SessionResponse(
                id=session.id,
                status=status,
                scenario_state=scenario_state,
            )
            self._sessions[session_id] = updated
            return updated
        return None

    def end_session(self, session_id: str) -> Optional[SessionResponse]:
        return self.update_session(
            session_id=session_id,
            scenario_state=ScenarioState.COMPLETED,
            status="ended",
        )

    def record_turn(self, session_id: str, turn_data: Dict[str, Any]) -> None:
        if session_id not in self._turns:
            self._turns[session_id] = []
        self._turns[session_id].append(turn_data)

    def get_turns(self, session_id: str) -> List[Dict[str, Any]]:
        return self._turns.get(session_id, [])

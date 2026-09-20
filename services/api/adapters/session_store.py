from uuid import uuid4

from services.api.domain.models import ScenarioState, TurnRecord


class InMemorySessionStore:
    def __init__(self):
        self.sessions: dict[str, ScenarioState] = {}

    def create_session(self) -> ScenarioState:
        state = ScenarioState(session_id=str(uuid4()))
        self.sessions[state.session_id] = state.model_copy(deep=True)
        return state

    def get_session(self, session_id: str) -> ScenarioState | None:
        state = self.sessions.get(session_id)
        return state.model_copy(deep=True) if state else None

    def update_session(self, session_id: str, state: ScenarioState) -> None:
        if session_id not in self.sessions or state.session_id != session_id:
            raise KeyError('Session not found')
        self.sessions[session_id] = state.model_copy(deep=True)

    def append_turn(self, session_id: str, turn: TurnRecord) -> None:
        self.sessions[session_id].history.append(turn.model_copy(deep=True))

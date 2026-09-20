from typing import Protocol

from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioState, TurnRecord


class ProviderError(RuntimeError):
    """Sanitized classifier failure that can cross the domain boundary."""

    def __init__(self, reason: str):
        allowed = {'timeout', 'connection', 'rate_limited', 'server_error',
                   'authentication', 'invalid_request', 'invalid_output',
                   'unavailable', 'not_configured'}
        self.reason = reason if reason in allowed else 'unavailable'
        super().__init__(self.reason)


class TacticClassifier(Protocol):
    async def classify(self, participant_text: str, scenario_state: ScenarioState,
                       conversation_history: list[TurnRecord]) -> ParticipantClassification: ...

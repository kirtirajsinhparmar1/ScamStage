from typing import Any, Protocol


class EvaluationProviderError(RuntimeError):
    """Sanitized evaluator failure; raw provider details never reach the UI."""

    _ALLOWED = {
        'timeout', 'connection', 'rate_limited', 'server_error',
        'authentication', 'invalid_request', 'invalid_output',
        'unavailable', 'not_configured',
    }

    def __init__(self, reason: str):
        self.reason = reason if reason in self._ALLOWED else 'unavailable'
        super().__init__(self.reason)


class ConversationEvaluator(Protocol):
    async def evaluate(self, state: Any) -> Any: ...

    async def close(self) -> None: ...

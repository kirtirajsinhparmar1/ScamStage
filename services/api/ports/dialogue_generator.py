from typing import Any, Protocol


class DialogueProviderError(RuntimeError):
    """Sanitized dialogue-provider failure that may cross the domain boundary."""

    _ALLOWED = {
        'timeout', 'connection', 'rate_limited', 'server_error',
        'authentication', 'invalid_request', 'invalid_output',
        'unavailable', 'not_configured',
    }

    def __init__(self, reason: str):
        self.reason = reason if reason in self._ALLOWED else 'unavailable'
        super().__init__(self.reason)


class DialogueGenerator(Protocol):
    async def generate(self, context: Any) -> Any: ...

    async def close(self) -> None: ...

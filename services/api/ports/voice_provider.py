from typing import Protocol

from services.api.domain.models import VoiceResult


class VoiceProvider(Protocol):
    async def synthesize(self, text: str, session_id: str, turn_id: str) -> VoiceResult: ...

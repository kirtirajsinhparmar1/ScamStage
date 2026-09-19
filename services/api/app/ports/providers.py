from typing import Protocol

from app.domain.enums import ScenarioState
from app.schemas.contracts import ClassificationResult


class TacticClassifier(Protocol):
    async def classify(self, text: str, context: ScenarioState) -> ClassificationResult: ...


class VoiceProvider(Protocol):
    async def synthesize(self, text: str) -> str | None: ...

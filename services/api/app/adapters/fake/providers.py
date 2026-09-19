from app.domain.enums import ScenarioState
from app.schemas.contracts import ClassificationResult


class FakeTacticClassifier:
    """Deterministic fixture behavior, not a real risk assessment."""

    async def classify(self, text: str, context: ScenarioState) -> ClassificationResult:
        skeptical = any(word in text.lower() for word in ("verify", "verification", "really"))
        return ClassificationResult(
            participant_intent="skeptical" if skeptical else "unknown",
            detected_tactics=["authority"] if context == ScenarioState.AUTHORITY else [],
            risk_level=0.25,
        )


class FakeVoiceProvider:
    async def synthesize(self, text: str) -> str | None:
        # Text-only mode: never return a URL pointing to nonexistent audio.
        return None

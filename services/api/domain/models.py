from pydantic import BaseModel, Field

from packages.contracts.session import ScenarioStage, ScenarioState
from packages.contracts.turn import TurnRecord

__all__ = ['ScenarioStage', 'ScenarioState', 'TurnRecord', 'VoiceResult', 'ScenarioDecision']


class VoiceResult(BaseModel):
    audio_url: str | None
    content_type: str | None
    provider: str
    used_fallback: bool
    error: str | None = None


class ScenarioDecision(BaseModel):
    next_stage: ScenarioStage
    scammer_text: str
    tactics_triggered: list[str]
    risk_score: float = Field(ge=0, le=1)
    completed: bool

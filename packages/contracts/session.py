from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .turn import TurnRecord


class ScenarioStage(str, Enum):
    authority = 'authority'
    urgency = 'urgency'
    verification_resistance = 'verification_resistance'
    action_request = 'action_request'
    safe_exit = 'safe_exit'
    risky_outcome = 'risky_outcome'


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_id: str = Field(default='fictional_bank_fraud_v1', min_length=1, max_length=80, pattern=r'^[a-z0-9_]+$')


class ScenarioState(BaseModel):
    session_id: str
    scenario_id: str = 'fictional_bank_fraud_v1'
    stage: ScenarioStage = ScenarioStage.authority
    risk_score: float = Field(default=0.2, ge=0, le=1)
    turn_count: int = 0
    history: list[TurnRecord] = Field(default_factory=list)
    completed: bool = False
    opening_text: str = ''
    opening_audio_url: str | None = None
    opening_voice_fallback: bool = True

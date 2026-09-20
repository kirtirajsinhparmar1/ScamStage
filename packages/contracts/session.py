from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .evaluation import EvaluationStatus, IndependentEvaluation
from .turn import InputMode, TurnRecord

InteractionMode = Literal['text', 'voice']


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
    interaction_mode: InteractionMode = 'text'


class ScenarioState(BaseModel):
    session_id: str
    scenario_id: str = 'fictional_bank_fraud_v1'
    interaction_mode: InteractionMode = 'text'
    stage: ScenarioStage = ScenarioStage.authority
    strategy: str = 'authority'
    risk_score: float = Field(default=0.2, ge=0, le=1)
    turn_count: int = 0
    history: list[TurnRecord] = Field(default_factory=list)
    completed: bool = False
    call_active: bool = True
    completion_reason: str | None = None
    opening_text: str = ''
    opening_audio_url: str | None = None
    opening_voice_fallback: bool = True
    opening_dialogue_provider: str = 'authored_fallback'
    opening_dialogue_fallback: bool = True
    opening_dialogue_fallback_reason: str | None = None
    opening_dialogue_pending: bool = False
    pending_participant_text: str | None = None
    pending_input_mode: InputMode | None = None
    dialogue_retry_available: bool = False
    evaluation_status: EvaluationStatus | None = None
    evaluation_provider: str | None = None
    evaluation_result: IndependentEvaluation | None = None

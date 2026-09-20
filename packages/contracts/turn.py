from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .classification import ParticipantClassification

ClassifierFallbackReason = Literal['timeout', 'connection', 'rate_limited', 'server_error',
    'authentication', 'invalid_request', 'invalid_output', 'unavailable', 'not_configured']
InputMode = Literal['text', 'voice']


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participant_text: str = Field(min_length=1, max_length=2000)
    input_mode: InputMode = 'text'

    @field_validator('participant_text')
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Participant text cannot be blank')
        return value.strip()


class TurnRecord(BaseModel):
    turn_id: str
    participant_text: str
    input_mode: InputMode = 'text'
    classification: ParticipantClassification
    stage_before: str
    stage_after: str
    strategy: str = 'authority'
    risk_before: float = Field(default=0.2, ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    scammer_text: str
    audio_url: str | None
    tactics_triggered: list[str]
    classifier_provider: str
    classifier_attempted: bool = False
    classifier_attempted_provider: str | None = None
    voice_provider: str
    classifier_fallback: bool
    classifier_fallback_reason: ClassifierFallbackReason | None = None
    voice_fallback: bool
    created_at: datetime
    dialogue_provider: str = 'authored_fallback'
    dialogue_fallback: bool = True
    dialogue_fallback_reason: str | None = None

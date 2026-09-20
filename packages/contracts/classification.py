from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal['safe_verification', 'skeptical', 'uncertain', 'compliant', 'safe_exit', 'irrelevant', 'refusal']


class ParticipantClassification(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participant_intent: Intent
    risk_signal: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_span: str = Field(max_length=240)

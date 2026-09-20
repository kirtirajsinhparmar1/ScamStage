from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EvaluationStatus = Literal['pending', 'complete', 'fallback', 'unavailable']
ParticipantOutcome = Literal['safe_exit', 'cautious', 'uncertain', 'risky']


class EvaluationEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')

    turn: int = Field(ge=1, le=8)
    quote: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=240)


class IndependentEvaluation(BaseModel):
    model_config = ConfigDict(extra='forbid')

    overall_risk: float = Field(ge=0, le=1)
    participant_outcome: ParticipantOutcome
    tactics_detected: list[str] = Field(default_factory=list, max_length=8)
    adaptation_summary: str = Field(min_length=1, max_length=500)
    participant_safety_summary: str = Field(min_length=1, max_length=500)
    evidence: list[EvaluationEvidence] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0, le=1)

    @field_validator('tactics_detected')
    @classmethod
    def clean_tactics(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 80 for value in cleaned):
            raise ValueError('Evaluation tactic labels are too long')
        return list(dict.fromkeys(cleaned))


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: EvaluationStatus
    provider: str | None = None
    result: IndependentEvaluation | None = None

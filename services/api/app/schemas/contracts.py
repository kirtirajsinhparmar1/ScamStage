from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Action, ScenarioState


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"


class ParticipantTurn(Contract):
    type: Literal["participant_turn"] = "participant_turn"
    text: str = Field(min_length=1, max_length=4000)
    input_mode: Literal["text", "voice"] = "text"


class ClassificationResult(Contract):
    participant_intent: Literal["unknown", "skeptical"] = "unknown"
    detected_tactics: list[str] = Field(default_factory=list)
    risk_level: float = Field(default=0, ge=0, le=1)


class TurnResult(Contract):
    type: Literal["turn_result"] = "turn_result"
    session_id: str = Field(min_length=1)
    speaker: Literal["scammer"] = "scammer"
    text: str
    audio_url: str | None = None
    scenario_state: ScenarioState
    detected_tactics: list[str] = Field(default_factory=list)
    risk_level: float = Field(ge=0, le=1)
    available_actions: list[Action]
    is_complete: bool


class SessionResponse(Contract):
    id: str = Field(min_length=1)
    status: Literal["active", "ended"] = "active"
    scenario_state: ScenarioState

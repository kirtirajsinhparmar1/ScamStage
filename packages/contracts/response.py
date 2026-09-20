from pydantic import BaseModel, Field

from .classification import ParticipantClassification
from .evaluation import EvaluationStatus, IndependentEvaluation
from .session import ScenarioStage, ScenarioState
from .turn import ClassifierFallbackReason

SIMULATION_NOTICE = 'This is a fictional scam-awareness training simulation. Use synthetic responses only. Never enter real credentials, personal information, or real verification codes.'


class SessionResponse(BaseModel):
    session_id: str
    scenario_id: str
    stage: ScenarioStage
    scammer_text: str
    audio_url: str | None
    voice_fallback: bool
    simulation_notice: str = SIMULATION_NOTICE
    risk_score: float
    interaction_mode: str = 'text'
    scenario_name: str = 'Fictional bank fraud'
    tactics_triggered: list[str] = Field(default_factory=lambda: ['authority'])
    dialogue_provider: str = 'authored_fallback'
    dialogue_fallback: bool = True


class Debrief(BaseModel):
    scenario_name: str
    outcome: str
    summary: str
    safer_response_guidance: list[str]
    completion_reason: str | None = None
    tactics_observed: list[str] = Field(default_factory=list)
    evaluation_status: EvaluationStatus | None = None
    evaluation_provider: str | None = None
    evaluation_result: IndependentEvaluation | None = None


class TurnResponse(BaseModel):
    turn_id: str
    participant_text: str
    analysis: ParticipantClassification
    stage_before: ScenarioStage
    stage_after: ScenarioStage
    risk_score: float = Field(ge=0, le=1)
    tactics_triggered: list[str]
    scammer_text: str
    audio_url: str | None
    classifier_provider: str
    voice_provider: str
    classifier_fallback: bool
    classifier_fallback_reason: ClassifierFallbackReason | None = None
    voice_fallback: bool
    completed: bool
    risk_before: float = Field(default=0.2, ge=0, le=1)
    debrief: Debrief | None = None
    input_mode: str = 'text'
    classifier_attempted: bool = False
    classifier_attempted_provider: str | None = None
    dialogue_provider: str = 'authored_fallback'
    dialogue_fallback: bool = True
    dialogue_fallback_reason: str | None = None


class SessionDetail(ScenarioState):
    timeline: list[dict]
    scenario_name: str = 'Fictional bank fraud'
    debrief: Debrief | None = None
    simulation_notice: str = SIMULATION_NOTICE

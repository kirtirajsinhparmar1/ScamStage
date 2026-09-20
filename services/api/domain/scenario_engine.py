from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioDecision, ScenarioStage as Stage, ScenarioState
from services.api.scenarios.catalog import ScenarioCatalog


class ScenarioEngine:
    def __init__(self, catalog: ScenarioCatalog | None = None):
        self.catalog = catalog or ScenarioCatalog()

    def decide(self, state: ScenarioState, classification: ParticipantClassification) -> ScenarioDecision:
        scenario = self.catalog.get(state.scenario_id)
        terminal = state.stage in {Stage.safe_exit, Stage.risky_outcome}
        next_stage = state.stage if terminal else scenario.transitions[state.stage][classification.participant_intent]
        risk = state.risk_score if terminal else round(max(0, min(1, state.risk_score + scenario.risk_deltas[classification.participant_intent])), 4)
        return ScenarioDecision(
            next_stage=next_stage, scammer_text=scenario.stages[next_stage],
            tactics_triggered=scenario.tactics[next_stage], risk_score=risk,
            completed=next_stage in {Stage.safe_exit, Stage.risky_outcome},
        )

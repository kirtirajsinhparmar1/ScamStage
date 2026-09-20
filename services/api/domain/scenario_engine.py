"""Deterministic, non-terminal pressure strategy selection.

The engine owns classification consequences, risk, tactics, and evidence
context. It deliberately does not write caller dialogue and never completes
an active call; the explicit end-call action owns terminal state.
"""

import re

from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioDecision, ScenarioStage as Stage, ScenarioState
from services.api.scenarios.catalog import ScenarioCatalog


ACTIVE_STAGES = {
    Stage.authority,
    Stage.urgency,
    Stage.verification_resistance,
    Stage.action_request,
}

_CLARIFICATION_RE = re.compile(
    r"\b(?:what happened|what is this about|what do you need|what exactly are you looking for|"
    r"what are you looking for|what is your name|why did you call|why are you calling|"
    r"can you repeat|could you repeat|what do you mean|please explain|which login|which transfer|"
    r"how can i verify|how do i verify|how may i verify)\b",
    re.IGNORECASE,
)

_STRATEGY_STAGE = {
    'authority': Stage.authority,
    'explanation': Stage.authority,
    'clarification': Stage.authority,
    'urgency': Stage.urgency,
    'verification_resistance': Stage.verification_resistance,
    'sensitive_request': Stage.action_request,
    'alternative_pressure': Stage.action_request,
    'repetition': Stage.action_request,
    'release': Stage.verification_resistance,
    're_anchor': Stage.authority,
}

_STRATEGY_TACTICS = {
    'authority': ('authority',),
    'explanation': ('explanation',),
    'clarification': ('clarification',),
    'urgency': ('urgency',),
    'verification_resistance': ('verification_pressure',),
    'sensitive_request': ('sensitive_information_request',),
    'alternative_pressure': ('pressure_escalation',),
    'repetition': ('repetition',),
    'release': ('release',),
    're_anchor': ('re_anchor',),
}


def _is_clarification_request(participant_text: str) -> bool:
    return bool(_CLARIFICATION_RE.search(' '.join(participant_text.lower().split())))


def _default_strategy(state: ScenarioState) -> str:
    sequence = ('explanation', 'urgency', 'clarification', 'verification_resistance', 'sensitive_request')
    return sequence[min(state.turn_count, len(sequence) - 1)]


class ScenarioEngine:
    def __init__(self, catalog: ScenarioCatalog | None = None):
        self.catalog = catalog or ScenarioCatalog()

    def _strategy_for(self, state: ScenarioState, classification: ParticipantClassification,
                     participant_text: str) -> str:
        intent = classification.participant_intent
        clarification = _is_clarification_request(participant_text)

        if intent == 'safe_verification':
            return 'verification_resistance'
        if intent == 'skeptical':
            return 'clarification'
        if intent == 'uncertain':
            if clarification:
                return 'clarification'
            return _default_strategy(state)
        if intent == 'compliant':
            return 'sensitive_request'
        if intent == 'refusal':
            return 'release' if state.strategy in {'sensitive_request', 'alternative_pressure'} else 'alternative_pressure'
        if intent == 'safe_exit':
            return 'release'
        if intent == 'irrelevant':
            return 're_anchor'
        return _default_strategy(state)

    def decide(self, state: ScenarioState, classification: ParticipantClassification,
               participant_text: str = '') -> ScenarioDecision:
        """Record one deterministic active-call beat without terminalizing it."""
        scenario = self.catalog.get(state.scenario_id)
        strategy = self._strategy_for(state, classification, participant_text)
        next_stage = _STRATEGY_STAGE.get(strategy, state.stage)
        if next_stage not in ACTIVE_STAGES:
            next_stage = Stage.authority

        risk = round(max(0, min(1, state.risk_score + scenario.risk_deltas[classification.participant_intent])), 4)
        tactics = list(scenario.tactics[next_stage])
        tactics.extend(_STRATEGY_TACTICS.get(strategy, ()))
        if classification.participant_intent in {'safe_verification', 'skeptical'}:
            tactics.append('verification_pressure')
        if classification.participant_intent == 'refusal':
            tactics.append('pressure_escalation')
        if classification.participant_intent == 'safe_exit':
            tactics.append('participant_boundary')

        # The text is intentionally empty. Ollama is the only active caller
        # wording author when the local dialogue provider is configured.
        return ScenarioDecision(
            next_stage=next_stage,
            strategy=strategy,
            scammer_text='',
            tactics_triggered=list(dict.fromkeys(tactics)),
            risk_score=risk,
            completed=False,
            completion_reason=None,
        )

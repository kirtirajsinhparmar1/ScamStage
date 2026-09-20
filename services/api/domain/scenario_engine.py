import hashlib

from packages.contracts.classification import ParticipantClassification
from services.api.domain.models import ScenarioDecision, ScenarioStage as Stage, ScenarioState
from services.api.scenarios.catalog import ScenarioCatalog

MAX_TURNS = 8

ADAPTIVE_VARIANTS = {
    'fictional_bank_fraud_v1': {
        Stage.urgency: [
            'The fictional alert is still open, and waiting could let the demo transfer proceed. Can you stay with me while we resolve it?',
            'I understand you want details, but this fictional security case is time-sensitive. The safest-looking choice is to act before the demo deadline.',
        ],
        Stage.verification_resistance: [
            'You can verify this later, but the fictional case reference is active now. Please keep the conversation here so I can finish the check.',
            'I hear your concern. This fictional caller says an outside callback could delay the alert, which is exactly the pressure you should notice.',
        ],
        Stage.action_request: [
            'To close the fictional alert, the caller now wants the pretend demo code DEMO-123. Never provide a real code; this is the pressure point to recognize.',
            'The fictional caller is moving from explanation to a sensitive-information request: a pretend demo code. Stop and verify independently instead of sharing anything real.',
        ],
    },
    'fictional_job_recruiter_v1': {
        Stage.urgency: [
            'The fictional hiring window is supposedly closing, so the recruiter pushes for an immediate answer before you can check the opportunity.',
            'A limited fictional role is being used as social pressure. Notice how the deadline is meant to make independent verification feel costly.',
        ],
        Stage.verification_resistance: [
            'The recruiter says checking the fictional company elsewhere could lose your place. That is verification pressure, not a reason to rush.',
            'This caller wants to stay in the same fictional conversation and frames independent checking as harmful to your application.',
        ],
        Stage.action_request: [
            'The fictional recruiter now pivots to a pretend onboarding fee or identity check. Never pay or send documents; the request is the training signal.',
            'The opportunity is now tied to a fictional upfront step. Pause before any payment or identity disclosure and verify the employer independently.',
        ],
    },
    'fictional_technical_support_v1': {
        Stage.urgency: [
            'The imaginary device alert is supposedly worsening, so the fictional caller uses fear to make careful verification feel too slow.',
            'The caller claims a fictional deadline is approaching for your demo files. Notice the fear-and-urgency combination before taking any action.',
        ],
        Stage.verification_resistance: [
            'The fictional support caller says an independent support channel cannot see this alert. That attempt to keep control is the tactic to spot.',
            'The caller discourages checking through a trusted support path and insists this fictional conversation is the only route to safety.',
        ],
        Stage.action_request: [
            'The fictional caller now asks for pretend remote access or payment. Never install software, grant access, or pay because an unsolicited caller demands it.',
            'Fear has become an action request: a fictional remote-access step and support payment. Stop and use a trusted support channel instead.',
        ],
    },
}

CLARIFICATION_RESPONSES = {
    'fictional_bank_fraud_v1': 'This fictional alert concerns an unusual demo login and a pretend transfer. No real account was accessed, but the caller wants you to feel pressure before you verify independently.',
    'fictional_job_recruiter_v1': 'The fictional recruiter says your demo profile was selected for a pretend remote role. Before discussing any fee or document, verify the employer through a trusted channel you find yourself.',
    'fictional_technical_support_v1': 'The fictional caller claims an imaginary device alert is active. Nothing real was checked or changed; the important question is whether you verify through trusted support before acting.',
}


def _is_clarification_request(participant_text: str) -> bool:
    lowered = ' '.join(participant_text.lower().split())
    return any(phrase in lowered for phrase in (
        'what happened', 'what is this about', 'what do you need',
        'what exactly are you looking for', 'what are you looking for',
        'what is your name', 'why did you call', 'why are you calling',
        'can you repeat', 'could you repeat', 'what do you mean', 'please explain',
        'which login', 'which transfer', 'how can i verify', 'how do i verify',
        'how may i verify',
    ))


class ScenarioEngine:
    def __init__(self, catalog: ScenarioCatalog | None = None):
        self.catalog = catalog or ScenarioCatalog()

    def decide(self, state: ScenarioState, classification: ParticipantClassification,
               participant_text: str = '') -> ScenarioDecision:
        scenario = self.catalog.get(state.scenario_id)
        terminal = state.stage in {Stage.safe_exit, Stage.risky_outcome}
        next_stage = state.stage if terminal else scenario.transitions[state.stage][classification.participant_intent]
        completion_reason = None
        clarification_intent = classification.participant_intent in {'uncertain', 'skeptical'}
        clarification_turn = clarification_intent and (
            classification.participant_intent == 'skeptical'
            or _is_clarification_request(participant_text)
        )
        prior_clarifications = sum(
            1
            for turn in state.history
            if turn.stage_before == state.stage.value
            and turn.classification.participant_intent in {'uncertain', 'skeptical'}
            and (
                turn.classification.participant_intent == 'skeptical'
                or _is_clarification_request(turn.participant_text)
            )
        )
        if (not terminal and state.interaction_mode == 'voice'
                and clarification_turn and prior_clarifications < 2):
            # Keep ordinary questions in the current deterministic stage for
            # two exchanges so the dialogue provider can answer them without
            # forcing an escalation or terminal outcome.
            next_stage = state.stage
        if not terminal and state.interaction_mode == 'voice' and classification.participant_intent == 'refusal':
            prior_refusals = sum(1 for turn in state.history if turn.classification.participant_intent == 'refusal')
            if prior_refusals == 0:
                # Voice callers apply one authored pressure beat before honoring
                # a continued refusal. Text mode keeps the milestone-2 table.
                next_stage = Stage.action_request if state.stage == Stage.action_request else Stage.urgency
        if not terminal and state.turn_count + 1 >= MAX_TURNS and next_stage not in {Stage.safe_exit, Stage.risky_outcome}:
            next_stage = Stage.safe_exit
            completion_reason = 'training_limit'
        risk = state.risk_score if terminal else round(max(0, min(1, state.risk_score + scenario.risk_deltas[classification.participant_intent])), 4)
        if next_stage in {Stage.safe_exit, Stage.risky_outcome} and completion_reason is None:
            completion_reason = next_stage.value
        text = scenario.stages[next_stage]
        tactics = list(scenario.tactics[next_stage])
        if state.interaction_mode == 'voice' and next_stage not in {Stage.safe_exit, Stage.risky_outcome}:
            if classification.participant_intent == 'uncertain' and _is_clarification_request(participant_text):
                text = CLARIFICATION_RESPONSES[state.scenario_id]
                tactics.append('clarification')
            else:
                variants = ADAPTIVE_VARIANTS.get(state.scenario_id, {}).get(next_stage, [])
                if variants:
                    seed = f'{state.session_id}:{state.turn_count + 1}:{classification.participant_intent}:{participant_text.strip().lower()}'
                    index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(variants)
                    text = variants[index]
            if classification.participant_intent in {'skeptical', 'safe_verification'}:
                tactics.append('verification_pressure')
            elif classification.participant_intent == 'uncertain':
                tactics.append('urgency_pressure')
            elif classification.participant_intent == 'refusal':
                tactics.append('pressure_escalation')
            elif classification.participant_intent == 'irrelevant':
                tactics.append('re_anchor')
        if completion_reason == 'training_limit':
            text = 'The fictional practice call reached its training limit. Pause here, review the pressure tactics, and verify unexpected requests independently.'
            tactics = list(dict.fromkeys(tactics + ['training_limit']))
        return ScenarioDecision(
            next_stage=next_stage, scammer_text=text,
            tactics_triggered=list(dict.fromkeys(tactics)), risk_score=risk,
            completed=next_stage in {Stage.safe_exit, Stage.risky_outcome},
            completion_reason=completion_reason,
        )

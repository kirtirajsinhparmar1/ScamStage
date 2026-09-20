import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from packages.contracts.evaluation import EvaluationResponse
from packages.contracts.response import Debrief, EndCallResponse, SessionDetail, SessionResponse, TurnResponse
from packages.contracts.session import InteractionMode, ScenarioStage
from packages.contracts.turn import TurnRequest
from services.api.adapters.gemini_dialogue import AuthoredDialogueGenerator
from services.api.domain.dialogue import DialogueContext, DialogueResult, sanitize_dialogue_text, validate_dialogue_result
from services.api.domain.fallback_classifier import FallbackClassifier
from services.api.domain.models import ScenarioDecision, ScenarioState, TurnRecord, VoiceResult
from services.api.domain.scenario_engine import ScenarioEngine
from services.api.ports.classifier import TacticClassifier
from services.api.ports.dialogue_generator import DialogueGenerator, DialogueProviderError
from services.api.ports.evaluator import ConversationEvaluator
from services.api.ports.session_store import SessionStore
from services.api.ports.voice_provider import VoiceProvider
from services.api.scenarios.catalog import DEFAULT_SCENARIO_ID, ScenarioCatalog

logger = logging.getLogger(__name__)

CALLER_NAMES = {
    'fictional_bank_fraud_v1': 'Mara Vale',
    'fictional_job_recruiter_v1': 'Eli Rowan',
    'fictional_technical_support_v1': 'Tessa Quill',
}


class SessionNotFound(Exception):
    pass


class SessionCompleted(Exception):
    pass


class DialogueRetryRequired(Exception):
    pass


class DialogueUnavailable(Exception):
    """Active local dialogue failed; do not advance the simulation silently."""

    def __init__(self, status: str, reason: str):
        self.status = status
        self.reason = reason
        super().__init__(status)


class TurnOrchestrator:
    def __init__(self, store: SessionStore, classifier: TacticClassifier, voice: VoiceProvider,
                 dialogue: DialogueGenerator | None = None,
                 evaluator: ConversationEvaluator | None = None):
        self.store, self.classifier, self.voice = store, classifier, voice
        self.authored_dialogue = AuthoredDialogueGenerator()
        self.dialogue = dialogue or self.authored_dialogue
        self.dialogue_enabled = dialogue is not None
        self.evaluator = evaluator
        self.evaluation_tasks: dict[str, asyncio.Task] = {}
        self.catalog = ScenarioCatalog()
        self.engine = ScenarioEngine(self.catalog)
        self.fallback = FallbackClassifier()
        self.locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _risk_band(score: float) -> str:
        if score >= 0.67:
            return 'high'
        if score >= 0.34:
            return 'medium'
        return 'low'

    @staticmethod
    def _caller_name(scenario_id: str) -> str:
        return CALLER_NAMES.get(scenario_id, 'A fictional caller')

    async def _speak(self, text: str, session_id: str, turn_id: str) -> VoiceResult:
        try:
            return await self.voice.synthesize(text, session_id, turn_id)
        except Exception:
            logger.warning('Voice fallback: provider unavailable')
            return VoiceResult(audio_url=None, content_type=None, provider='fallback', used_fallback=True,
                               error='Voice unavailable')

    def _opening_context(self, state: ScenarioState) -> DialogueContext:
        scenario = self.catalog.get(state.scenario_id)
        return DialogueContext(
            scenario_id=state.scenario_id,
            scenario_name=scenario.display_name,
            fictional_organization=scenario.fictional_organization,
            fictional_caller_name=self._caller_name(state.scenario_id),
            stage=ScenarioStage.authority.value,
            strategy='authority',
            # The first line is deliberately narrower than the scenario's
            # authored stage tactics: opening Ollama wording may establish
            # fictional authority and a vague alert, but must not introduce
            # urgency or a sensitive-request frame before the participant has
            # spoken.
            allowed_tactics=('authority',),
            participant_intent='uncertain',
            participant_text='',
            response_purpose='opening_authority',
            authored_text=scenario.opening_message,
            recent_turns=(),
            tactic_history=(),
            risk_before=state.risk_score,
            risk_after=state.risk_score,
            risk_band=self._risk_band(state.risk_score),
        )

    async def _generate_provider_dialogue(self, context: DialogueContext) -> DialogueResult:
        provider_name = getattr(self.dialogue, 'provider_name', 'gemini')
        try:
            result = await self.dialogue.generate(context)
            result = validate_dialogue_result(result, context)
            if result.provider != provider_name or result.used_fallback:
                raise DialogueProviderError('invalid_output')
            logger.info('Caller dialogue routing: provider=%s fallback=false validation_passed=true', provider_name)
            return result
        except DialogueProviderError as exc:
            reason = exc.reason
        except Exception:
            reason = 'unavailable'

        if provider_name == 'ollama':
            status = {
                'timeout': 'ollama_timeout',
                'invalid_output': 'ollama_invalid_output',
            }.get(reason, 'ollama_unavailable')
            logger.info('Caller dialogue routing: provider=%s fallback=true reason=%s status=%s',
                        status, reason, status)
            raise DialogueUnavailable(status, reason)

        logger.info('Caller dialogue routing: provider=authored_fallback fallback=true reason=%s', reason)
        fallback = await self.authored_dialogue.generate(context)
        return fallback.model_copy(update={'error': reason})

    async def _opening_dialogue(self, state: ScenarioState) -> DialogueResult:
        context = self._opening_context(state)
        if not self.dialogue_enabled:
            result = await self.authored_dialogue.generate(context)
            logger.info('Caller dialogue routing: provider=authored_fallback fallback=true reason=not_configured')
            return result
        return await self._generate_provider_dialogue(context)

    async def create_session(self, scenario_id: str = DEFAULT_SCENARIO_ID,
                             interaction_mode: InteractionMode = 'text') -> SessionResponse:
        scenario = self.catalog.get(scenario_id)
        state = self.store.create_session()
        state.scenario_id = scenario.id
        state.interaction_mode = interaction_mode
        state.risk_score = scenario.initial_risk
        state.strategy = 'authority'
        state.call_active = True
        self.locks[state.session_id] = asyncio.Lock()

        try:
            dialogue = await self._opening_dialogue(state)
        except DialogueUnavailable as exc:
            state.opening_text = ''
            state.opening_audio_url = None
            state.opening_voice_fallback = True
            state.opening_dialogue_provider = exc.status
            state.opening_dialogue_fallback = True
            state.opening_dialogue_fallback_reason = exc.reason
            state.opening_dialogue_pending = True
            state.dialogue_retry_available = True
            self.store.update_session(state.session_id, state)
            return self._session_response(state, scenario)

        state.opening_text = dialogue.caller_text
        state.opening_dialogue_provider = dialogue.provider
        state.opening_dialogue_fallback = dialogue.used_fallback
        state.opening_dialogue_fallback_reason = dialogue.error
        state.opening_dialogue_pending = False
        state.dialogue_retry_available = False
        voice = await self._speak(state.opening_text, state.session_id, 'opening')
        state.opening_audio_url, state.opening_voice_fallback = voice.audio_url, voice.used_fallback
        self.store.update_session(state.session_id, state)
        return self._session_response(state, scenario, voice=voice)

    def _session_response(self, state: ScenarioState, scenario=None, voice: VoiceResult | None = None) -> SessionResponse:
        scenario = scenario or self.catalog.get(state.scenario_id)
        return SessionResponse(
            session_id=state.session_id,
            scenario_id=state.scenario_id,
            stage=state.stage,
            scammer_text=state.opening_text,
            audio_url=state.opening_audio_url if voice is None else voice.audio_url,
            voice_fallback=state.opening_voice_fallback if voice is None else voice.used_fallback,
            risk_score=state.risk_score,
            interaction_mode=state.interaction_mode,
            scenario_name=scenario.display_name,
            tactics_triggered=list(scenario.tactics[ScenarioStage.authority]),
            dialogue_provider=state.opening_dialogue_provider,
            dialogue_fallback=state.opening_dialogue_fallback,
            dialogue_fallback_reason=state.opening_dialogue_fallback_reason,
            strategy=state.strategy,
            call_active=state.call_active,
            retry_available=state.dialogue_retry_available,
        )

    def _debrief(self, state: ScenarioState) -> Debrief | None:
        if not state.completed:
            return None
        scenario = self.catalog.get(state.scenario_id)
        tactics_observed = list(scenario.tactics[ScenarioStage.authority])
        boundaries: list[str] = []
        evidence: list[str] = []
        verification_requested = False
        for turn in state.history:
            tactics_observed.extend(turn.tactics_triggered)
            intent = turn.classification.participant_intent
            if turn.classification.evidence_span and turn.classification.evidence_span not in evidence:
                evidence.append(turn.classification.evidence_span)
            if intent == 'safe_verification':
                verification_requested = True
                boundaries.append('Requested independent verification before acting.')
            elif intent == 'safe_exit':
                boundaries.append('Stated an intention to end the call or use a trusted channel.')
            elif intent == 'refusal':
                boundaries.append('Refused the caller’s requested action.')
            elif intent == 'uncertain' and any(
                token in turn.participant_text.lower() for token in ('what', 'why', 'how', 'could', 'can you')
            ):
                boundaries.append('Asked for clarification before acting.')
            if any(token in turn.participant_text.lower() for token in ('verify', 'official', 'trusted channel')):
                verification_requested = True
        boundaries = list(dict.fromkeys(boundaries))
        if not boundaries:
            boundaries = ['No explicit protective boundary was recorded before the call ended.']
        safer = list(dict.fromkeys([
            *scenario.safer_response_guidance,
            'Ask for time and verify through a contact method you locate independently.',
            'Never provide real credentials, payment details, or authentication codes to an unexpected caller.',
        ]))
        summary = (
            'You ended the fictional call with the End call safely control. The fast safety policy recorded '
            f'{len(state.history)} participant turn(s) and a training risk indicator of '
            f'{round(state.risk_score * 100)}%. This is an educational training indicator, not a personal assessment; '
            'no real action occurred.'
        )
        return Debrief(
            scenario_name=scenario.display_name,
            outcome='user_ended_call',
            summary=summary,
            safer_response_guidance=safer,
            safer_response_examples=safer,
            completion_reason=state.completion_reason,
            tactics_observed=list(dict.fromkeys(tactics_observed)),
            training_risk_score=state.risk_score,
            boundaries_set=boundaries,
            verification_requested=verification_requested,
            evidence=evidence,
            evaluation_status=state.evaluation_status,
            evaluation_provider=state.evaluation_provider,
            evaluation_result=state.evaluation_result,
        )

    def _dialogue_context(self, state: ScenarioState, participant_text: str, classification,
                          decision: ScenarioDecision) -> DialogueContext:
        scenario = self.catalog.get(state.scenario_id)
        transcript_messages: list[dict[str, str]] = []
        for turn in state.history:
            transcript_messages.extend((
                {'role': 'participant', 'text': sanitize_dialogue_text(turn.participant_text)},
                {'role': 'caller', 'text': sanitize_dialogue_text(turn.scammer_text)},
            ))
        recent = tuple(transcript_messages[-8:])
        tactics = tuple(tactic for turn in state.history[-8:] for tactic in turn.tactics_triggered)
        return DialogueContext(
            scenario_id=state.scenario_id,
            scenario_name=scenario.display_name,
            fictional_organization=scenario.fictional_organization,
            fictional_caller_name=self._caller_name(state.scenario_id),
            stage=decision.next_stage.value,
            strategy=decision.strategy,
            allowed_tactics=tuple(decision.tactics_triggered),
            participant_intent=classification.participant_intent,
            participant_text=sanitize_dialogue_text(participant_text),
            response_purpose=decision.strategy,
            authored_text=scenario.stages[decision.next_stage],
            recent_turns=recent,
            tactic_history=tactics,
            risk_before=state.risk_score,
            risk_after=decision.risk_score,
            risk_band=self._risk_band(decision.risk_score),
        )

    async def _dialogue_for(self, state: ScenarioState, participant_text: str,
                            classification, decision: ScenarioDecision) -> DialogueResult:
        context = self._dialogue_context(state, participant_text, classification, decision)
        if not self.dialogue_enabled:
            logger.info('Caller dialogue routing: provider=authored_fallback fallback=true reason=not_configured')
            return await self.authored_dialogue.generate(context)
        return await self._generate_provider_dialogue(context)

    def _schedule_evaluation(self, session_id: str) -> None:
        if self.evaluator is None:
            state = self.store.get_session(session_id)
            if state is not None:
                state.evaluation_status = 'fallback'
                state.evaluation_provider = 'deterministic_fallback'
                self.store.update_session(session_id, state)
            return
        existing = self.evaluation_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        self.evaluation_tasks[session_id] = asyncio.create_task(self._evaluate_session(session_id))

    async def _evaluate_session(self, session_id: str) -> None:
        state = self.store.get_session(session_id)
        if state is None or self.evaluator is None:
            return
        try:
            result = await self.evaluator.evaluate(state)
        except Exception:
            logger.warning('Independent evaluation unavailable; retaining deterministic debrief')
            latest = self.store.get_session(session_id)
            if latest is not None:
                latest.evaluation_status = 'fallback'
                latest.evaluation_provider = 'deterministic_fallback'
                latest.evaluation_result = None
                self.store.update_session(session_id, latest)
            return
        latest = self.store.get_session(session_id)
        if latest is not None:
            latest.evaluation_status = 'complete'
            latest.evaluation_provider = 'nemotron'
            latest.evaluation_result = result
            self.store.update_session(session_id, latest)

    def get_evaluation(self, session_id: str) -> EvaluationResponse:
        state = self.store.get_session(session_id)
        if state is None:
            raise SessionNotFound()
        return EvaluationResponse(
            status=state.evaluation_status or 'unavailable',
            provider=state.evaluation_provider,
            result=state.evaluation_result,
        )

    def _timeline(self, state: ScenarioState) -> list[dict]:
        timeline = [{
            'turn_id': turn.turn_id,
            'stage_before': turn.stage_before,
            'stage_after': turn.stage_after,
            'strategy': turn.strategy,
            'risk_score': turn.risk_score,
            'tactics_triggered': turn.tactics_triggered,
            'evidence_span': turn.classification.evidence_span,
            'risk_before': turn.risk_before,
            'risk_after': turn.risk_score,
            'detected_response_category': turn.classification.participant_intent,
            'confidence': turn.classification.confidence,
            'input_mode': turn.input_mode,
            'classifier_provider': turn.classifier_provider,
            'classifier_attempted': turn.classifier_attempted,
            'dialogue_provider': turn.dialogue_provider,
            'dialogue_fallback': turn.dialogue_fallback,
        } for turn in state.history]
        if state.completed:
            timeline.append({
                'event': 'call_ended',
                'completion_reason': state.completion_reason,
                'strategy': state.strategy,
                'risk_before': state.risk_score,
                'risk_after': state.risk_score,
            })
        return timeline

    def get_session(self, session_id: str) -> SessionDetail:
        state = self.store.get_session(session_id)
        if state is None:
            raise SessionNotFound()
        return SessionDetail(
            **state.model_dump(),
            scenario_name=self.catalog.get(state.scenario_id).display_name,
            debrief=self._debrief(state),
            timeline=self._timeline(state),
        )

    async def _classify(self, state: ScenarioState, participant_text: str, input_mode: str):
        del input_mode
        classification = self.fallback.classify_fast(participant_text, state, state.history[-8:])
        logger.info('Active turn classifier: provider=fast_safety_policy attempted=false')
        return classification, 'fast_safety_policy', False, None, None

    async def _process_turn_locked(self, state: ScenarioState, request: TurnRequest,
                                   *, retry: bool = False) -> TurnResponse:
        participant_text = request.participant_text
        if not retry:
            if state.dialogue_retry_available:
                raise DialogueRetryRequired()
            state.pending_participant_text = participant_text
            state.pending_input_mode = request.input_mode
            state.dialogue_retry_available = True
            self.store.update_session(state.session_id, state)

        before = state.stage
        classification, classifier_provider, classifier_attempted, fallback_reason, attempted_provider = await self._classify(
            state, participant_text, request.input_mode,
        )
        classifier_fallback = classifier_provider == 'fallback'
        if not classification.evidence_span or classification.evidence_span not in participant_text:
            classification.evidence_span = participant_text[:240]
        decision = self.engine.decide(state, classification, participant_text)
        dialogue = await self._dialogue_for(state, participant_text, classification, decision)
        turn_id = str(uuid4())
        voice = await self._speak(dialogue.caller_text, state.session_id, turn_id)
        turn = TurnRecord(
            turn_id=turn_id,
            participant_text=participant_text,
            input_mode=request.input_mode,
            classification=classification,
            stage_before=before.value,
            stage_after=decision.next_stage.value,
            strategy=decision.strategy,
            risk_before=state.risk_score,
            risk_score=decision.risk_score,
            scammer_text=dialogue.caller_text,
            audio_url=voice.audio_url,
            tactics_triggered=decision.tactics_triggered,
            classifier_provider=classifier_provider,
            classifier_attempted=classifier_attempted,
            classifier_attempted_provider=attempted_provider,
            voice_provider=voice.provider,
            classifier_fallback=classifier_fallback,
            voice_fallback=voice.used_fallback,
            classifier_fallback_reason=fallback_reason,
            created_at=datetime.now(timezone.utc),
            dialogue_provider=dialogue.provider,
            dialogue_fallback=dialogue.used_fallback,
            dialogue_fallback_reason=dialogue.error,
        )
        state.stage = decision.next_stage
        state.strategy = decision.strategy
        state.risk_score = decision.risk_score
        state.completed = False
        state.call_active = True
        state.completion_reason = None
        state.turn_count += 1
        state.history.append(turn)
        state.pending_participant_text = None
        state.pending_input_mode = None
        state.dialogue_retry_available = False
        self.store.update_session(state.session_id, state)
        payload = turn.model_dump(exclude={'classification', 'created_at'})
        return TurnResponse(**payload, analysis=classification, completed=False, debrief=None, retry_available=False)

    async def submit_turn(self, session_id: str, participant_text: str,
                          input_mode: str = 'text') -> TurnResponse:
        if self.store.get_session(session_id) is None:
            raise SessionNotFound()
        request = TurnRequest(participant_text=participant_text, input_mode=input_mode)
        async with self.locks[session_id]:
            state = self.store.get_session(session_id)
            if state.completed:
                raise SessionCompleted()
            return await self._process_turn_locked(state, request)

    async def retry_dialogue(self, session_id: str) -> SessionResponse | TurnResponse:
        if self.store.get_session(session_id) is None:
            raise SessionNotFound()
        async with self.locks[session_id]:
            state = self.store.get_session(session_id)
            if state.completed:
                raise SessionCompleted()
            if state.opening_dialogue_pending:
                dialogue = await self._opening_dialogue(state)
                state.opening_text = dialogue.caller_text
                state.opening_dialogue_provider = dialogue.provider
                state.opening_dialogue_fallback = dialogue.used_fallback
                state.opening_dialogue_fallback_reason = dialogue.error
                state.opening_dialogue_pending = False
                state.dialogue_retry_available = False
                voice = await self._speak(state.opening_text, state.session_id, 'opening')
                state.opening_audio_url, state.opening_voice_fallback = voice.audio_url, voice.used_fallback
                self.store.update_session(session_id, state)
                return self._session_response(state, self.catalog.get(state.scenario_id), voice=voice)
            if not state.pending_participant_text or not state.dialogue_retry_available:
                raise DialogueRetryRequired()
            request = TurnRequest(
                participant_text=state.pending_participant_text,
                input_mode=state.pending_input_mode or 'text',
            )
            return await self._process_turn_locked(state, request, retry=True)

    async def end_call(self, session_id: str) -> EndCallResponse:
        if self.store.get_session(session_id) is None:
            raise SessionNotFound()
        async with self.locks[session_id]:
            state = self.store.get_session(session_id)
            if state.completed:
                raise SessionCompleted()
            state.completed = True
            state.call_active = False
            state.completion_reason = 'user_ended_call'
            state.opening_dialogue_pending = False
            state.pending_participant_text = None
            state.pending_input_mode = None
            state.dialogue_retry_available = False
            state.evaluation_status = 'pending' if self.evaluator is not None else 'fallback'
            state.evaluation_provider = 'nemotron' if self.evaluator is not None else 'deterministic_fallback'
            self.store.update_session(session_id, state)
            self._schedule_evaluation(session_id)
            debrief = self._debrief(state)
            return EndCallResponse(
                session_id=state.session_id,
                scenario_id=state.scenario_id,
                scenario_name=self.catalog.get(state.scenario_id).display_name,
                stage=state.stage,
                strategy=state.strategy,
                risk_score=state.risk_score,
                completed=True,
                call_active=False,
                completion_reason=state.completion_reason,
                debrief=debrief,
                timeline=self._timeline(state),
            )


__all__ = [
    'DialogueRetryRequired', 'DialogueUnavailable', 'SessionCompleted', 'SessionNotFound', 'TurnOrchestrator',
]

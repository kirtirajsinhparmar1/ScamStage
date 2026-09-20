import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from packages.contracts.evaluation import EvaluationResponse
from packages.contracts.response import Debrief, SessionDetail, SessionResponse, TurnResponse
from packages.contracts.session import InteractionMode
from packages.contracts.turn import TurnRequest
from services.api.adapters.gemini_dialogue import AuthoredDialogueGenerator
from services.api.domain.dialogue import DialogueContext, DialogueResult, sanitize_dialogue_text, validate_dialogue_result
from services.api.domain.fallback_classifier import FallbackClassifier
from services.api.domain.models import TurnRecord, VoiceResult
from services.api.domain.scenario_engine import ScenarioEngine
from services.api.ports.classifier import ProviderError, TacticClassifier
from services.api.ports.dialogue_generator import DialogueGenerator, DialogueProviderError
from services.api.ports.evaluator import ConversationEvaluator
from services.api.ports.session_store import SessionStore
from services.api.ports.voice_provider import VoiceProvider
from services.api.scenarios.catalog import DEFAULT_SCENARIO_ID, ScenarioCatalog
from services.api.domain.models import ScenarioStage

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


class SessionCompleted(Exception):
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

    async def _speak(self, text: str, session_id: str, turn_id: str) -> VoiceResult:
        try:
            return await self.voice.synthesize(text, session_id, turn_id)
        except Exception:
            logger.warning('Voice fallback: provider unavailable')
            return VoiceResult(audio_url=None, content_type=None, provider='fallback', used_fallback=True, error='Voice unavailable')

    async def create_session(self, scenario_id: str = DEFAULT_SCENARIO_ID,
                             interaction_mode: InteractionMode = 'text') -> SessionResponse:
        scenario = self.catalog.get(scenario_id)
        state = self.store.create_session()
        state.scenario_id = scenario.id
        state.interaction_mode = interaction_mode
        state.risk_score = scenario.initial_risk
        self.locks[state.session_id] = asyncio.Lock()
        state.opening_text = scenario.opening_message
        voice = await self._speak(state.opening_text, state.session_id, 'opening')
        state.opening_audio_url, state.opening_voice_fallback = voice.audio_url, voice.used_fallback
        self.store.update_session(state.session_id, state)
        return SessionResponse(session_id=state.session_id, scenario_id=state.scenario_id,
            stage=state.stage, scammer_text=state.opening_text, audio_url=voice.audio_url,
            voice_fallback=voice.used_fallback, risk_score=state.risk_score,
            interaction_mode=state.interaction_mode, scenario_name=scenario.display_name,
            tactics_triggered=scenario.tactics[state.stage])

    def _debrief(self, state) -> Debrief | None:
        if not state.completed:
            return None
        scenario = self.catalog.get(state.scenario_id)
        # The opening authority tactic is part of every completed exercise,
        # even when the terminal stage itself has no tactic label.
        tactics_observed = list(scenario.tactics[ScenarioStage.authority])
        for turn in state.history:
            tactics_observed.extend(turn.tactics_triggered)
        return Debrief(scenario_name=scenario.display_name, outcome=state.stage.value,
            summary=scenario.debrief[state.stage],
            safer_response_guidance=scenario.safer_response_guidance,
            completion_reason=state.completion_reason,
            tactics_observed=list(dict.fromkeys(tactics_observed)),
            evaluation_status=state.evaluation_status,
            evaluation_provider=state.evaluation_provider,
            evaluation_result=state.evaluation_result)

    def _dialogue_context(self, state, participant_text: str, classification, decision) -> DialogueContext:
        scenario = self.catalog.get(state.scenario_id)
        recent = tuple({
            'participant': sanitize_dialogue_text(turn.participant_text),
            'scammer_text': sanitize_dialogue_text(turn.scammer_text),
        } for turn in state.history[-4:])
        tactics = tuple(tactic for turn in state.history[-4:] for tactic in turn.tactics_triggered)
        return DialogueContext(
            scenario_id=state.scenario_id,
            fictional_organization=scenario.fictional_organization,
            stage=decision.next_stage.value,
            allowed_tactics=tuple(decision.tactics_triggered),
            participant_intent=classification.participant_intent,
            participant_text=sanitize_dialogue_text(participant_text),
            response_purpose=decision.next_stage.value,
            authored_text=decision.scammer_text,
            recent_turns=recent,
            tactic_history=tactics,
            risk_before=state.risk_score,
            risk_after=decision.risk_score,
        )

    async def _dialogue_for(self, state, participant_text: str, classification, decision) -> DialogueResult:
        # Terminal wording is a safety boundary. Gemini never gets an
        # opportunity to continue a safe exit or author a risky outcome.
        if decision.completed or not self.dialogue_enabled:
            reason = 'policy_terminal' if decision.completed else 'not_configured'
            logger.info('Caller dialogue routing: provider=authored_fallback fallback=true reason=%s', reason)
            return DialogueResult(
                caller_text=decision.scammer_text,
                tone='calm' if decision.completed else 'urgent',
                provider='authored_fallback',
                used_fallback=True,
                error=reason,
            )
        context = self._dialogue_context(state, participant_text, classification, decision)
        provider_name = getattr(self.dialogue, 'provider_name', 'gemini')
        try:
            result = await self.dialogue.generate(context)
            result = validate_dialogue_result(result, context)
            if result.provider != provider_name or result.used_fallback:
                raise DialogueProviderError('invalid_output')
            logger.info(
                'Caller dialogue routing: provider=%s fallback=false validation_passed=true',
                provider_name,
            )
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
            logger.info(
                'Caller dialogue routing: provider=%s fallback=true reason=%s status=%s',
                status, reason, status,
            )
            # In Ollama mode, a failed active request must not advance the
            # conversation with authored wording. The request is rejected
            # before the session state or history is updated.
            raise DialogueUnavailable(status, reason)

        logger.info('Caller dialogue routing: provider=authored_fallback fallback=true reason=%s', reason)
        fallback = await self.authored_dialogue.generate(context)
        return fallback.model_copy(update={'error': reason})

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

    def get_session(self, session_id: str) -> SessionDetail:
        state = self.store.get_session(session_id)
        if state is None:
            raise SessionNotFound()
        return SessionDetail(**state.model_dump(), scenario_name=self.catalog.get(state.scenario_id).display_name,
            debrief=self._debrief(state), timeline=[{
            'turn_id': turn.turn_id, 'stage_before': turn.stage_before,
            'stage_after': turn.stage_after, 'risk_score': turn.risk_score,
            'tactics_triggered': turn.tactics_triggered,
            'evidence_span': turn.classification.evidence_span,
            'risk_before': turn.risk_before, 'risk_after': turn.risk_score,
            'detected_response_category': turn.classification.participant_intent,
            'confidence': turn.classification.confidence,
            'input_mode': turn.input_mode,
            'classifier_provider': turn.classifier_provider,
            'classifier_attempted': turn.classifier_attempted,
            'dialogue_provider': turn.dialogue_provider,
            'dialogue_fallback': turn.dialogue_fallback,
        } for turn in state.history])

    async def submit_turn(self, session_id: str, participant_text: str,
                          input_mode: str = 'text') -> TurnResponse:
        if self.store.get_session(session_id) is None:
            raise SessionNotFound()
        request = TurnRequest(participant_text=participant_text, input_mode=input_mode)
        participant_text = request.participant_text
        async with self.locks[session_id]:
            state = self.store.get_session(session_id)
            if state.completed:
                raise SessionCompleted()
            before = state.stage
            fallback = False
            fallback_reason = None
            voice_path = state.interaction_mode == 'voice' or request.input_mode == 'voice'
            if voice_path:
                # Voice turns must be local and bounded; a hosted classifier is
                # intentionally not on this critical path.
                classification = self.fallback.classify_fast(participant_text, state, state.history[-4:])
                classifier_provider = 'fast_safety_policy'
                classifier_attempted = False
                classifier_attempted_provider = None
                logger.info('Live turn classifier: provider=fast_safety_policy attempted=false')
            else:
                classifier_attempted = True
                classifier_attempted_provider = 'nemotron'
                try:
                    classification = await self.classifier.classify(participant_text, state, state.history[-4:])
                    classifier_provider = 'nemotron'
                except Exception as exc:
                    logger.warning('Classifier fallback: Nemotron unavailable or output invalid')
                    classification = await self.fallback.classify(participant_text, state, state.history[-4:])
                    fallback = True
                    classifier_provider = 'fallback'
                    fallback_reason = exc.reason if isinstance(exc, ProviderError) else 'unavailable'
            if not classification.evidence_span or classification.evidence_span not in participant_text:
                classification.evidence_span = participant_text[:240]
            decision = self.engine.decide(state, classification, participant_text)
            dialogue = await self._dialogue_for(state, participant_text, classification, decision)
            turn_id = str(uuid4())
            voice = await self._speak(dialogue.caller_text, session_id, turn_id)
            turn = TurnRecord(turn_id=turn_id, participant_text=participant_text,
                input_mode=request.input_mode,
                classification=classification, stage_before=before.value, stage_after=decision.next_stage.value,
                risk_before=state.risk_score, risk_score=decision.risk_score, scammer_text=dialogue.caller_text, audio_url=voice.audio_url,
                tactics_triggered=decision.tactics_triggered, classifier_provider=classifier_provider,
                classifier_attempted=classifier_attempted, classifier_attempted_provider=classifier_attempted_provider,
                voice_provider=voice.provider, classifier_fallback=fallback, voice_fallback=voice.used_fallback,
                classifier_fallback_reason=fallback_reason,
                created_at=datetime.now(timezone.utc), dialogue_provider=dialogue.provider,
                dialogue_fallback=dialogue.used_fallback, dialogue_fallback_reason=dialogue.error)
            state.stage, state.risk_score, state.completed = decision.next_stage, decision.risk_score, decision.completed
            state.completion_reason = decision.completion_reason
            state.turn_count += 1
            state.history.append(turn)
            # One snapshot update keeps stage, count and history consistent for readers.
            if state.completed and state.evaluation_status is None:
                state.evaluation_status = 'pending' if self.evaluator is not None else 'fallback'
                state.evaluation_provider = 'nemotron' if self.evaluator is not None else 'deterministic_fallback'
            self.store.update_session(session_id, state)
            if state.completed:
                self._schedule_evaluation(session_id)
            payload = turn.model_dump(exclude={'classification', 'created_at'})
            return TurnResponse(**payload, analysis=classification, completed=state.completed,
                debrief=self._debrief(state))

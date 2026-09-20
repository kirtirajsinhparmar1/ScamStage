import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from packages.contracts.response import Debrief, SessionDetail, SessionResponse, TurnResponse
from packages.contracts.turn import TurnRequest
from services.api.domain.fallback_classifier import FallbackClassifier
from services.api.domain.models import TurnRecord, VoiceResult
from services.api.domain.scenario_engine import ScenarioEngine
from services.api.ports.classifier import ProviderError, TacticClassifier
from services.api.ports.session_store import SessionStore
from services.api.ports.voice_provider import VoiceProvider
from services.api.scenarios.catalog import DEFAULT_SCENARIO_ID, ScenarioCatalog

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


class SessionCompleted(Exception):
    pass


class TurnOrchestrator:
    def __init__(self, store: SessionStore, classifier: TacticClassifier, voice: VoiceProvider):
        self.store, self.classifier, self.voice = store, classifier, voice
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

    async def create_session(self, scenario_id: str = DEFAULT_SCENARIO_ID) -> SessionResponse:
        scenario = self.catalog.get(scenario_id)
        state = self.store.create_session()
        state.scenario_id = scenario.id
        state.risk_score = scenario.initial_risk
        self.locks[state.session_id] = asyncio.Lock()
        state.opening_text = scenario.opening_message
        voice = await self._speak(state.opening_text, state.session_id, 'opening')
        state.opening_audio_url, state.opening_voice_fallback = voice.audio_url, voice.used_fallback
        self.store.update_session(state.session_id, state)
        return SessionResponse(session_id=state.session_id, scenario_id=state.scenario_id,
            stage=state.stage, scammer_text=state.opening_text, audio_url=voice.audio_url,
            voice_fallback=voice.used_fallback, risk_score=state.risk_score,
            scenario_name=scenario.display_name, tactics_triggered=scenario.tactics[state.stage])

    def _debrief(self, state) -> Debrief | None:
        if not state.completed:
            return None
        scenario = self.catalog.get(state.scenario_id)
        return Debrief(scenario_name=scenario.display_name, outcome=state.stage.value,
            summary=scenario.debrief[state.stage],
            safer_response_guidance=scenario.safer_response_guidance)

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
        } for turn in state.history])

    async def submit_turn(self, session_id: str, participant_text: str) -> TurnResponse:
        if self.store.get_session(session_id) is None:
            raise SessionNotFound()
        participant_text = TurnRequest(participant_text=participant_text).participant_text
        async with self.locks[session_id]:
            state = self.store.get_session(session_id)
            if state.completed:
                raise SessionCompleted()
            before = state.stage
            fallback = False
            fallback_reason = None
            try:
                classification = await self.classifier.classify(participant_text, state, state.history[-4:])
            except Exception as exc:
                logger.warning('Classifier fallback: Nemotron unavailable or output invalid')
                classification = await self.fallback.classify(participant_text, state, state.history[-4:])
                fallback = True
                fallback_reason = exc.reason if isinstance(exc, ProviderError) else 'unavailable'
            if not classification.evidence_span or classification.evidence_span not in participant_text:
                classification.evidence_span = participant_text[:240]
            decision = self.engine.decide(state, classification)
            turn_id = str(uuid4())
            voice = await self._speak(decision.scammer_text, session_id, turn_id)
            turn = TurnRecord(turn_id=turn_id, participant_text=participant_text,
                classification=classification, stage_before=before.value, stage_after=decision.next_stage.value,
                risk_before=state.risk_score, risk_score=decision.risk_score, scammer_text=decision.scammer_text, audio_url=voice.audio_url,
                tactics_triggered=decision.tactics_triggered, classifier_provider='fallback' if fallback else 'nemotron',
                voice_provider=voice.provider, classifier_fallback=fallback, voice_fallback=voice.used_fallback,
                classifier_fallback_reason=fallback_reason,
                created_at=datetime.now(timezone.utc))
            state.stage, state.risk_score, state.completed = decision.next_stage, decision.risk_score, decision.completed
            state.turn_count += 1
            state.history.append(turn)
            # One snapshot update keeps stage, count and history consistent for readers.
            self.store.update_session(session_id, state)
            payload = turn.model_dump(exclude={'classification', 'created_at'})
            return TurnResponse(**payload, analysis=classification, completed=state.completed,
                debrief=self._debrief(state))

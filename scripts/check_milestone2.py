"""Offline catalog and HTTP regression checks; never call paid providers."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from pydantic import ValidationError

from packages.contracts.classification import ParticipantClassification
from services.api.config import Settings
from services.api.main import create_app
from services.api.scenarios.catalog import DEFAULT_SCENARIO_ID, ScenarioCatalog, ScenarioDefinition


SCENARIO_IDS = {
    'fictional_bank_fraud_v1',
    'fictional_job_recruiter_v1',
    'fictional_technical_support_v1',
}

# Explicit fixtures isolate deterministic scenario behavior from both live
# availability and the keyword fallback classifier's evolving vocabulary.
FIXTURE_INTENTS = {
    'I will call the number on my card instead.': 'safe_verification',
    'I will follow those instructions.': 'compliant',
    'I am hanging up.': 'safe_exit',
    'I refuse.': 'refusal',
    'I will verify independently.': 'safe_verification',
    'Hmm': 'uncertain',
    'This sounds suspicious.': 'skeptical',
}


async def fixture_classification(text, state, history):
    return ParticipantClassification(participant_intent=FIXTURE_INTENTS[text],
                                    risk_signal=.5, confidence=.9, evidence_span=text)


class CatalogChecks(unittest.TestCase):
    def test_catalog_has_three_valid_scenarios(self):
        catalog = ScenarioCatalog()
        self.assertEqual({item['id'] for item in catalog.list_scenarios()}, SCENARIO_IDS)
        for identifier in SCENARIO_IDS:
            with self.subTest(scenario=identifier):
                definition = catalog.get(identifier)
                self.assertEqual(ScenarioDefinition.model_validate(definition.model_dump()).id, identifier)
                self.assertTrue(definition.safer_response_guidance)

    def test_invalid_definitions_are_rejected(self):
        valid = ScenarioCatalog().get().model_dump(mode='json')
        invalid = []
        for field in ['stages', 'tactics', 'transitions', 'risk_deltas', 'debrief']:
            candidate = deepcopy(valid)
            candidate[field].pop(next(iter(candidate[field])))
            invalid.append(candidate)
        for field, value in [('opening_message', 'unmatched'), ('initial_risk', 2),
                             ('safer_response_guidance', []), ('safer_response_guidance', [' '])]:
            candidate = deepcopy(valid)
            candidate[field] = value
            invalid.append(candidate)
        for value in [float('nan'), float('inf'), -2]:
            candidate = deepcopy(valid)
            candidate['risk_deltas']['uncertain'] = value
            invalid.append(candidate)
        candidate = deepcopy(valid)
        candidate['transitions']['authority']['compliant'] = 'not_a_stage'
        invalid.append(candidate)
        candidate = deepcopy(valid)
        candidate['transitions']['authority'].pop('compliant')
        invalid.append(candidate)
        for index, candidate in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValidationError):
                ScenarioDefinition.model_validate(candidate)

    def test_duplicate_and_missing_default_catalog_rejected(self):
        default = ScenarioCatalog().get()
        with self.assertRaises(ValueError):
            ScenarioCatalog([default, default])
        with self.assertRaises(ValueError):
            ScenarioCatalog([])

    def test_retrieved_definitions_cannot_mutate_catalog(self):
        catalog = ScenarioCatalog()
        retrieved = catalog.get()
        retrieved.stages.clear()
        self.assertTrue(catalog.get().stages)


class ApiChecks(unittest.TestCase):
    def setUp(self):
        self.audio = TemporaryDirectory(prefix='scamstage-tests-')
        self.addCleanup(self.audio.cleanup)
        settings = Settings(_env_file=None, dialogue_provider='authored', ollama_enabled=False,
                            nemotron_api_key='', elevenlabs_api_key='',
                            elevenlabs_voice_id='', audio_dir=Path(self.audio.name))
        self.app = create_app(settings)
        self.client = self.enterContext(TestClient(self.app))
        self.real_classify = self.app.state.orchestrator.classifier.classify
        self.enterContext(patch.object(self.app.state.orchestrator.classifier, 'classify',
                                       AsyncMock(side_effect=fixture_classification)))

    def create(self, scenario_id=DEFAULT_SCENARIO_ID):
        response = self.client.post('/api/sessions', json={'scenario_id': scenario_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def turn(self, session_id, text):
        response = self.client.post(f'/api/sessions/{session_id}/turns', json={'participant_text': text})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def end(self, session_id):
        response = self.client.post(f'/api/sessions/{session_id}/end')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_safe_public_catalog(self):
        response = self.client.get('/api/scenarios')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.json()}, SCENARIO_IDS)
        allowed = {'id', 'display_name', 'description', 'fictional_organization', 'safer_response_guidance'}
        for row in response.json():
            self.assertLessEqual(set(row), allowed)
            self.assertTrue(all(row[key] for key in ['id', 'display_name', 'description', 'fictional_organization']))

    def test_default_session_backward_compatibility(self):
        for kwargs in [{}, {'json': {}}, {'json': {'scenario_id': DEFAULT_SCENARIO_ID}}]:
            with self.subTest(request=kwargs):
                response = self.client.post('/api/sessions', **kwargs)
                self.assertEqual(response.status_code, 200, response.text)
                session = response.json()
                self.assertEqual(session['scenario_id'], DEFAULT_SCENARIO_ID)
                self.assertEqual(session['stage'], 'authority')
                self.assertIn('Lumenvale', session['scammer_text'])
                turn = self.turn(session['session_id'], 'I will call the number on my card instead.')
                self.assertEqual(turn['stage_after'], 'verification_resistance')
                self.assertFalse(turn['completed'])
                self.assertIsNone(turn['debrief'])
                turn = self.turn(session['session_id'], 'I will follow those instructions.')
                self.assertEqual(turn['stage_after'], 'action_request')
                self.assertFalse(turn['completed'])
                self.assertIsNone(turn['debrief'])
                ended = self.end(session['session_id'])
                self.assertTrue(ended['completed'])
                self.assertFalse(ended['call_active'])
                self.assertEqual(ended['debrief']['outcome'], 'user_ended_call')

    def test_invalid_scenario_does_not_create_state(self):
        store = self.app.state.orchestrator.store
        for invalid in ['unknown_scenario', '', None, 12]:
            with self.subTest(identifier=invalid):
                response = self.client.post('/api/sessions', json={'scenario_id': invalid})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertFalse(store.sessions)
                self.assertFalse(self.app.state.orchestrator.locks)

    def test_safe_exit_refusal_and_verification_all_scenarios(self):
        for identifier in SCENARIO_IDS:
            for text, category in [('I am hanging up.', 'safe_exit'), ('I refuse.', 'refusal')]:
                with self.subTest(scenario=identifier, category=category):
                    session = self.create(identifier)
                    turn = self.turn(session['session_id'], text)
                    self.assertEqual(turn['analysis']['participant_intent'], category)
                    self.assertNotIn(turn['stage_after'], {'safe_exit', 'risky_outcome'})
                    self.assertFalse(turn['completed'])
                    self.assertIsNone(turn['debrief'])
                    self.assertTrue(self.client.get(f"/api/sessions/{session['session_id']}").json()['call_active'])
                    ended = self.end(session['session_id'])
                    self.assertEqual(ended['debrief']['scenario_name'], session['scenario_name'])
                    self.assertEqual(ended['debrief']['outcome'], 'user_ended_call')
            session = self.create(identifier)
            first = self.turn(session['session_id'], 'I will verify independently.')
            self.assertEqual(first['stage_after'], 'verification_resistance')
            second = self.turn(session['session_id'], 'I will verify independently.')
            self.assertEqual(second['stage_after'], 'verification_resistance')
            self.assertFalse(second['completed'])
            self.assertIsNone(second['debrief'])
            self.end(session['session_id'])

    def test_five_conversation_turns_remain_active_all_scenarios(self):
        texts = [
            'What exactly happened with this alert?',
            'This sounds suspicious; why are you rushing me?',
            'I am uncomfortable sharing anything on this call.',
            'I will follow those instructions.',
            'I am hanging up now.',
        ]
        for identifier in SCENARIO_IDS:
            with self.subTest(scenario=identifier):
                session = self.create(identifier)
                scores = [session['risk_score']]
                for text in texts:
                    turn = self.turn(session['session_id'], text)
                    self.assertFalse(turn['completed'])
                    self.assertIsNone(turn['debrief'])
                    self.assertTrue(turn['tactics_triggered'])
                    self.assertEqual(turn['classifier_provider'], 'fast_safety_policy')
                    self.assertFalse(turn['classifier_fallback'])
                    self.assertEqual(len(self.client.get(
                        f"/api/sessions/{session['session_id']}"
                    ).json()['history']), len(scores))
                    scores.append(turn['risk_score'])
                detail = self.client.get(f"/api/sessions/{session['session_id']}").json()
                self.assertTrue(detail['call_active'])
                self.assertFalse(detail['completed'])
                self.assertEqual(len(detail['timeline']), 5)
                self.assertGreaterEqual(len(set(scores)), 2)
                ended = self.end(session['session_id'])
                self.assertTrue(ended['completed'])
                self.assertEqual(ended['debrief']['outcome'], 'user_ended_call')

    def test_skeptical_branch_preserves_bank_and_verifies_new_scenarios(self):
        for identifier in SCENARIO_IDS:
            with self.subTest(scenario=identifier):
                session = self.create(identifier)
                turn = self.turn(session['session_id'], 'This sounds suspicious.')
                self.assertEqual(turn['stage_after'], 'authority')
                self.assertEqual(turn['strategy'], 'clarification')
                self.assertEqual(turn['analysis']['participant_intent'], 'skeptical')
                self.assertFalse(turn['completed'])
                self.end(session['session_id'])

    def test_timeline_and_terminal_history_are_consistent(self):
        for identifier in SCENARIO_IDS:
            with self.subTest(scenario=identifier):
                session = self.create(identifier)
                turn = self.turn(session['session_id'], 'I am hanging up.')
                path = f"/api/sessions/{session['session_id']}"
                detail = self.client.get(path).json()
                self.assertEqual(len(detail['history']), 1)
                self.assertIsNone(detail['debrief'])
                self.assertIsNone(turn['debrief'])
                entry = detail['timeline'][0]
                for key, expected in {
                    'stage_before': turn['stage_before'], 'stage_after': turn['stage_after'],
                    'risk_before': turn['risk_before'], 'risk_after': turn['risk_score'],
                    'detected_response_category': turn['analysis']['participant_intent'],
                    'confidence': turn['analysis']['confidence'],
                    'evidence_span': turn['analysis']['evidence_span'],
                    'tactics_triggered': turn['tactics_triggered'],
                }.items():
                    self.assertEqual(entry[key], expected)
                response = self.client.post(path + '/turns', json={'participant_text': 'Hmm'})
                self.assertEqual(response.status_code, 200)
                ended = self.end(session['session_id'])
                self.assertEqual(ended['debrief'], self.client.get(path).json()['debrief'])
                self.assertEqual(ended['timeline'][-1]['event'], 'call_ended')
                response = self.client.post(path + '/turns', json={'participant_text': 'Hmm'})
                self.assertEqual(response.status_code, 409)

    def test_missing_providers_use_fallback(self):
        self.app.state.orchestrator.classifier.classify = self.real_classify
        session = self.create()
        self.assertTrue(session['voice_fallback'])
        self.assertIsNone(session['audio_url'])
        turn = self.turn(session['session_id'], 'This sounds suspicious.')
        self.assertEqual(turn['analysis']['participant_intent'], 'skeptical')
        self.assertFalse(turn['classifier_fallback'])
        self.assertEqual(turn['classifier_provider'], 'fast_safety_policy')
        self.assertIsNone(turn['classifier_fallback_reason'])
        self.assertTrue(turn['voice_fallback'])
        self.assertIsNone(turn['audio_url'])
        self.assertIn(turn['analysis']['evidence_span'], turn['participant_text'])

    def test_failed_providers_use_fallback(self):
        orchestrator = self.app.state.orchestrator
        with patch.object(orchestrator.classifier, 'classify', AsyncMock(side_effect=RuntimeError('unavailable'))), \
             patch.object(orchestrator.voice, 'synthesize', AsyncMock(side_effect=RuntimeError('unavailable'))):
            session = self.create()
            turn = self.turn(session['session_id'], 'I refuse.')
            self.assertTrue(session['voice_fallback'])
            self.assertTrue(turn['voice_fallback'])
            self.assertFalse(turn['classifier_fallback'])
            self.assertEqual(turn['classifier_provider'], 'fast_safety_policy')
            self.assertFalse(turn['completed'])

    def test_active_turns_use_fast_policy_without_external_classifier(self):
        with patch.object(self.app.state.orchestrator.classifier, 'classify',
                          AsyncMock(side_effect=AssertionError('external classifier must not run'))):
            session = self.create()
            turn = self.turn(session['session_id'], 'I refuse.')
            self.assertEqual(turn['classifier_provider'], 'fast_safety_policy')
            self.assertFalse(turn['classifier_attempted'])
            self.assertFalse(turn['classifier_fallback'])
            self.assertFalse(turn['completed'])

    def test_invented_classifier_evidence_is_repaired(self):
        classification = ParticipantClassification(participant_intent='uncertain', risk_signal=.5,
                                                 confidence=.7, evidence_span='invented evidence')
        with patch.object(self.app.state.orchestrator.classifier, 'classify', AsyncMock(return_value=classification)):
            session = self.create()
            turn = self.turn(session['session_id'], 'A fictional response with no matched phrase.')
            self.assertIn(turn['analysis']['evidence_span'], turn['participant_text'])
            self.assertNotEqual(turn['analysis']['evidence_span'], 'invented evidence')
            detail = self.client.get(f"/api/sessions/{session['session_id']}").json()
            self.assertEqual(detail['timeline'][0]['evidence_span'], turn['analysis']['evidence_span'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

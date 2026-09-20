"""Offline SDK/transport reliability checks. No requests leave MockTransport."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from openai import AsyncOpenAI

from services.api.adapters.nemotron.classifier import NemotronClassifier
from services.api.adapters.nemotron.client import ProviderError
from services.api.config import Settings
from services.api.domain.models import ScenarioState


TEXT = 'Synthetic fixture response.'
SECRET = 'DO_NOT_LOG_SECRET_FIXTURE'
LOGGER = 'services.api.adapters.nemotron'


def completion(content=None):
    if content is None:
        content = json.dumps(dict(participant_intent='uncertain', risk_signal=.5,
                                  confidence=.9, evidence_span=TEXT))
    return httpx.Response(200, json={
        'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'fixture',
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                     'finish_reason': 'stop'}],
    })


class NemotronChecks(unittest.IsolatedAsyncioTestCase):
    async def adapter(self, outcomes, **settings):
        self.requests = []
        remaining = iter(outcomes)

        def handle(request):
            self.requests.append(request)
            outcome = next(remaining)
            if isinstance(outcome, type) and issubclass(outcome, Exception):
                raise outcome(SECRET, request=request)
            if isinstance(outcome, int):
                return httpx.Response(outcome, json={'error': {'message': SECRET}},
                                      headers={'X-Private-Fixture': SECRET})
            return outcome

        def client(**kwargs):
            return AsyncOpenAI(http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handle)), **kwargs)

        config = Settings(_env_file=None, nemotron_api_key=SECRET, **settings)
        with patch('services.api.adapters.nemotron.client.AsyncOpenAI', side_effect=client):
            adapter = NemotronClassifier(config)
        self.addAsyncCleanup(adapter.close)
        return adapter

    async def classify(self, adapter):
        return await adapter.classify(TEXT, ScenarioState(session_id='fixture'), [])

    async def test_explicit_timeouts_and_short_generation_budget(self):
        adapter = await self.adapter([completion()], nemotron_timeout_seconds=17,
                                     nemotron_temperature=1, nemotron_max_tokens=1024)
        self.assertEqual(adapter.client.timeout.as_dict(),
                         dict(connect=5, read=17, write=10, pool=5))
        self.assertEqual(adapter.client.max_retries, 0)
        original_timeout = asyncio.timeout
        with patch('services.api.adapters.nemotron.classifier.asyncio.timeout',
                   wraps=original_timeout) as deadline:
            result = await self.classify(adapter)
        deadline.assert_called_once_with(37)
        body = json.loads(self.requests[0].content)
        self.assertEqual(body['temperature'], 0)
        self.assertEqual(body['max_tokens'], 128)
        self.assertFalse(body['stream'])
        self.assertEqual(body['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(result.participant_intent, 'uncertain')
        self.assertEqual(len(self.requests), 1)

    async def test_transient_second_attempt_succeeds(self):
        for first in [httpx.ReadTimeout, httpx.ConnectError, 429, 500, 503]:
            with self.subTest(first=first):
                adapter = await self.adapter([first, completion()])
                with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                           new_callable=AsyncMock) as sleep:
                    result = await self.classify(adapter)
                self.assertEqual(result.participant_intent, 'uncertain')
                self.assertEqual(len(self.requests), 2)
                sleep.assert_awaited_once_with(.5)

    async def test_transient_exhaustion_is_bounded_and_sanitized(self):
        for failure, reason in [(httpx.ReadTimeout, 'timeout'),
                                (httpx.ConnectTimeout, 'timeout'),
                                (httpx.WriteTimeout, 'timeout'),
                                (httpx.PoolTimeout, 'timeout'),
                                (httpx.ConnectError, 'connection'),
                                (429, 'rate_limited'), (500, 'server_error')]:
            with self.subTest(failure=failure):
                adapter = await self.adapter([failure, failure])
                with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                           new_callable=AsyncMock) as sleep, \
                     self.assertLogs(LOGGER, level='WARNING') as logs, \
                     self.assertRaises(ProviderError) as caught:
                    await self.classify(adapter)
                self.assertEqual(caught.exception.reason, reason)
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertEqual(len(self.requests), 2)
                sleep.assert_awaited_once_with(.5)
                output = '\n'.join(logs.output)
                self.assertIn('nemotron', output.lower())
                self.assertIn('elapsed', output.lower())
                self.assertIn(reason, output)
                self.assertNotIn(SECRET, output)
                self.assertNotIn(TEXT, output)

    async def test_permanent_http_failures_never_retry(self):
        for status, reason in [(400, 'invalid_request'), (401, 'authentication'),
                               (403, 'authentication'), (404, 'invalid_request'),
                               (408, 'invalid_request'), (422, 'invalid_request')]:
            with self.subTest(status=status):
                adapter = await self.adapter([status])
                with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                           new_callable=AsyncMock) as sleep, \
                     self.assertRaises(ProviderError) as caught:
                    await self.classify(adapter)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(len(self.requests), 1)
                sleep.assert_not_awaited()

    async def test_invalid_output_never_retries(self):
        for content in ['not json ' + SECRET, '{}', '{"participant_intent":"invented"}']:
            with self.subTest(content=content):
                adapter = await self.adapter([completion(content)])
                with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                           new_callable=AsyncMock) as sleep, \
                     self.assertRaises(ProviderError) as caught:
                    await self.classify(adapter)
                self.assertEqual(caught.exception.reason, 'invalid_output')
                self.assertEqual(len(self.requests), 1)
                sleep.assert_not_awaited()

    async def test_evidence_sanitation_preserves_schema(self):
        content = json.dumps(dict(participant_intent='uncertain', risk_signal=.5,
                                  confidence=.7, evidence_span=SECRET))
        adapter = await self.adapter([completion(content)])
        result = await self.classify(adapter)
        self.assertIn(result.evidence_span, TEXT)
        self.assertNotIn(SECRET, result.evidence_span)

    async def test_production_failure_logging_is_silent(self):
        adapter = await self.adapter([503, 503], app_env='production')
        with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                   new_callable=AsyncMock), self.assertNoLogs(LOGGER), \
             self.assertRaises(ProviderError):
            await self.classify(adapter)

    async def test_not_configured_does_not_request_or_retry(self):
        adapter = NemotronClassifier(Settings(_env_file=None, nemotron_api_key=''))
        self.addAsyncCleanup(adapter.close)
        with patch('services.api.adapters.nemotron.classifier.asyncio.sleep',
                   new_callable=AsyncMock) as sleep, self.assertRaises(ProviderError) as caught:
            await self.classify(adapter)
        self.assertEqual(caught.exception.reason, 'not_configured')
        sleep.assert_not_awaited()


if __name__ == '__main__':
    unittest.main(verbosity=2)

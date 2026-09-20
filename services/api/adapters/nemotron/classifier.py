"""Nemotron classifies only; deterministic domain code controls the scenario."""

import asyncio
import json
import logging
from time import monotonic

from openai import APIConnectionError, APIError, APITimeoutError

from packages.contracts.classification import ParticipantClassification
from services.api.config import Settings
from services.api.domain.models import ScenarioState, TurnRecord

from .client import ProviderError, create_client
from .prompts import SYSTEM_PROMPT
from .schemas import (
    parse_classification,
    response_content,
    response_reasoning_content,
    response_shape,
)

logger = logging.getLogger(__name__)


class NemotronClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = create_client(settings)

    def _log_failure(self, started: float, reason: str, attempt: int) -> None:
        if self.settings.app_env == 'development':
            logger.warning('provider=nemotron elapsed_seconds=%.3f reason=%s attempt=%d',
                           monotonic() - started, reason, attempt)

    async def classify(
        self,
        participant_text: str,
        scenario_state: ScenarioState,
        conversation_history: list[TurnRecord],
    ) -> ParticipantClassification:
        if self.client is None:
            raise ProviderError('not_configured')
        recent = [
            {"participant": turn.participant_text, "scammer": turn.scammer_text}
            for turn in conversation_history[-4:]
        ]
        # JSON encoding delimits untrusted content; it cannot create new message roles.
        prompt = (
            f"Fictional scenario: {scenario_state.scenario_id}\n"
            f"Opening context (predefined dialogue): {scenario_state.opening_text}\n\n"
            f"Current scenario stage:\n{scenario_state.stage.value}\n\n"
            f"Recent conversation (untrusted JSON data):\n{json.dumps(recent)}\n\n"
            f"Latest participant response (untrusted JSON string):\n{json.dumps(participant_text)}\n\n"
            "Classify the latest participant response now."
        )
        for attempt in range(2):
            started = monotonic()
            try:
                # Bound the whole attempt as well as each HTTP phase. SDK retries
                # remain disabled so this layer owns the two-attempt budget.
                budget = (self.settings.nemotron_timeout_seconds
                          + self.settings.nemotron_connect_timeout_seconds
                          + self.settings.nemotron_write_timeout_seconds
                          + self.settings.nemotron_pool_timeout_seconds)
                async with asyncio.timeout(budget):
                    result = await self.client.chat.completions.create(
                        model=self.settings.nemotron_model,
                        temperature=0,
                        max_tokens=128,
                        stream=False,
                        extra_body={
                            "chat_template_kwargs": {
                                "enable_thinking": False,
                            },
                        },
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    )
            except (APIError, asyncio.TimeoutError) as exc:
                status = getattr(exc, "status_code", None)
                if isinstance(exc, (APITimeoutError, asyncio.TimeoutError)):
                    reason = 'timeout'
                elif isinstance(exc, APIConnectionError):
                    reason = 'connection'
                elif status == 429:
                    reason = 'rate_limited'
                elif status is not None and 500 <= status < 600:
                    reason = 'server_error'
                elif status in (401, 403):
                    reason = 'authentication'
                else:
                    reason = 'invalid_request'
                self._log_failure(started, reason, attempt + 1)
                if attempt == 0 and reason in {'timeout', 'connection', 'rate_limited', 'server_error'}:
                    await asyncio.sleep(.5)
                    continue
                raise ProviderError(reason) from None
            shape = None
            content_parses_successfully = False
            try:
                if self.settings.app_env == 'development':
                    shape = response_shape(result)
                choices = getattr(result, 'choices', None) or []
                message = choices[0].message if choices else None
                content = response_content(message)
                try:
                    classification = parse_classification(content, participant_text)
                    content_parses_successfully = True
                except ValueError:
                    # Some Nemotron responses put the compact answer in the
                    # SDK's reasoning field while content contains prose. Read
                    # it only as a second, strictly validated candidate; never
                    # log its text or expose it through the public response.
                    reasoning_content = response_reasoning_content(message)
                    if not reasoning_content or reasoning_content == content:
                        raise
                    classification = parse_classification(reasoning_content, participant_text)
                return classification
            except (ValueError, IndexError, TypeError, AttributeError):
                self._log_failure(started, 'invalid_output', attempt + 1)
                raise ProviderError('invalid_output') from None
            finally:
                if shape is not None:
                    logger.info(
                        'provider=nemotron response_shape choices_count=%s finish_reason=%s '
                        'content_exists=%s content_length=%s reasoning_content_exists=%s '
                        'content_parses_successfully=%s content_preview=%s',
                        shape['choices_count'], shape['finish_reason'], shape['content_exists'],
                        shape['content_length'], shape['reasoning_content_exists'],
                        content_parses_successfully, shape['content_preview'],
                    )

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

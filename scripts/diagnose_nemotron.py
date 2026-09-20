"""One synthetic live request; emit only safe transport diagnostics."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.adapters.nemotron.client import create_client
from services.api.adapters.nemotron.schemas import (
    parse_classification,
    response_content,
    response_shape,
)
from services.api.config import Settings


async def main():
    logging.disable(logging.CRITICAL)
    settings = Settings()
    client = create_client(settings)
    if client is None:
        print(json.dumps({'exception_type': 'NotConfigured', 'elapsed_seconds': 0,
                          'sanitized_error_category': 'not_configured'}))
        return
    timeout = client.timeout
    report = {'configured_timeout_seconds': {
        key: getattr(timeout, key, timeout) for key in ('connect', 'read', 'write', 'pool')
    }, 'configured_nemotron_timeout_seconds': settings.nemotron_timeout_seconds,
              'finish_reason': None, 'reasoning_content_exists': None,
              'content_parses_successfully': None}
    started = monotonic()
    try:
        async with asyncio.timeout(sum(report['configured_timeout_seconds'].values())):
            response = await client.chat.completions.with_raw_response.create(
                model=settings.nemotron_model, temperature=0,
                max_tokens=128, stream=False,
                extra_body={'chat_template_kwargs': {'enable_thinking': False}},
                messages=[{'role': 'system', 'content': (
                    'Classify the synthetic response. Return exactly one compact JSON object '
                    'with participant_intent, risk_signal, confidence, evidence_span only. '
                    'Return nothing else: no reasoning, markdown, or explanation.'
                )}, {'role': 'user', 'content': 'I am hanging up.'}],
                )
        parsed = response.parse()
        shape = response_shape(parsed)
        choices = getattr(parsed, 'choices', None) or []
        message = choices[0].message if choices else None
        content = response_content(message)
        try:
            parse_classification(content, 'I am hanging up.')
        except (ValueError, TypeError, AttributeError):
            content_parses_successfully = False
        else:
            content_parses_successfully = True
        report.update(
            http_status=response.status_code,
            sanitized_error_category='none',
            finish_reason=shape['finish_reason'],
            reasoning_content_exists=shape['reasoning_content_exists'],
            content_parses_successfully=content_parses_successfully,
        )
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        kind = type(exc).__name__
        category = ('timeout' if 'Timeout' in kind else 'connection' if 'Connection' in kind
                    else 'rate_limited' if status == 429 else 'authentication' if status in (401, 403)
                    else 'server_error' if status and status >= 500 else 'request_error')
        report.update(exception_type=kind, sanitized_error_category=category)
        if status:
            report['http_status'] = status
    finally:
        report['elapsed_seconds'] = round(monotonic() - started, 3)
        await client.close()
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(main())

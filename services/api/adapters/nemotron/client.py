"""A bounded, non-streaming OpenAI-compatible NVIDIA client."""

import httpx
from openai import AsyncOpenAI

from services.api.config import Settings
from services.api.ports.classifier import ProviderError


def create_client(settings: Settings) -> AsyncOpenAI | None:
    if not settings.nemotron_api_key:
        return None
    return AsyncOpenAI(
        base_url=settings.nemotron_base_url,
        api_key=settings.nemotron_api_key,
        timeout=httpx.Timeout(
            connect=settings.nemotron_connect_timeout_seconds,
            read=settings.nemotron_timeout_seconds,
            write=settings.nemotron_write_timeout_seconds,
            pool=settings.nemotron_pool_timeout_seconds,
        ),
        max_retries=0,
    )

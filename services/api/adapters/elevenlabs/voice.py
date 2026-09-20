"""Text-to-speech adapter with an explicit text-only degraded mode."""

import asyncio
import logging

import httpx

from services.api.config import Settings
from services.api.domain.models import VoiceResult

from .audio_store import AudioStore, safe_id
from .client import ElevenLabsClient

logger = logging.getLogger(__name__)


class ElevenLabsVoiceProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ElevenLabsClient(settings)
        self.store = AudioStore(settings.audio_dir, settings.public_audio_path)

    @staticmethod
    def fallback(reason: str) -> VoiceResult:
        logger.warning("ElevenLabs text-only fallback: %s", reason)
        return VoiceResult(
            audio_url=None, content_type=None, provider="fallback", used_fallback=True, error=reason
        )

    async def synthesize(self, text: str, session_id: str, turn_id: str) -> VoiceResult:
        if not self.settings.elevenlabs_api_key or not self.settings.elevenlabs_voice_id:
            return self.fallback("Voice credentials are not configured")
        if not text.strip() or len(text) > 1500:
            return self.fallback("Voice text is outside allowed length")
        try:
            safe_id(session_id)
            safe_id(turn_id, opening=True)
            async with asyncio.timeout(self.settings.elevenlabs_timeout_seconds):
                data = await self.client.generate(text)
            audio_url = self.store.save(data, session_id, turn_id)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "ElevenLabs request failed type=%s status=%s",
                type(exc).__name__,
                exc.response.status_code,
            )
            return self.fallback("ElevenLabs request was rejected")
        except (httpx.TimeoutException, TimeoutError) as exc:
            logger.warning("ElevenLabs request failed type=%s", type(exc).__name__)
            return self.fallback("ElevenLabs request timed out")
        except httpx.HTTPError as exc:
            logger.warning("ElevenLabs request failed type=%s", type(exc).__name__)
            return self.fallback("ElevenLabs network request failed")
        except (OSError, ValueError) as exc:
            logger.warning("ElevenLabs audio handling failed type=%s", type(exc).__name__)
            return self.fallback("ElevenLabs audio could not be stored")
        except Exception as exc:
            logger.warning("ElevenLabs provider failed type=%s", type(exc).__name__)
            return self.fallback("Voice generation or audio storage failed")
        return VoiceResult(
            audio_url=audio_url, content_type="audio/mpeg", provider="elevenlabs",
            used_fallback=False, error=None,
        )

    async def close(self) -> None:
        await self.client.close()

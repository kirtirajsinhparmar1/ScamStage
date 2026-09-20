"""ElevenLabs voice provider — Person 3 implementation.

Uses the ElevenLabs text-to-speech API via httpx to synthesize speech
and return an audio URL.
"""

import httpx

_DEFAULT_BASE_URL = "https://api.elevenlabs.io/v1"
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" — a common default voice


class ElevenLabsVoiceProvider:
    """Real ElevenLabs-backed voice provider.

    Sends text to the ElevenLabs TTS endpoint and returns the audio URL.
    Returns ``None`` on failure so callers always have a text fallback.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        voice_id: str = _DEFAULT_VOICE_ID,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._voice_id = voice_id
        self._timeout = timeout

    async def synthesize(self, text: str) -> str | None:
        """Convert *text* to speech and return the audio URL, or ``None`` on failure."""
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/text-to-speech/{self._voice_id}",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                # The ElevenLabs API returns audio bytes directly.
                # In a full implementation you'd store the audio in object storage
                # and return a signed URL. For now we return None since we don't
                # have storage wired up yet.
                # TODO(person3): Save audio bytes to object storage, return URL
                return None
        except httpx.HTTPError:
            # Graceful degradation: text-only mode on voice failure.
            return None

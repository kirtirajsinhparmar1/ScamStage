"""ElevenLabs HTTP transport; API credentials remain on the backend."""

from urllib.parse import quote

import httpx

from services.api.config import Settings


class ElevenLabsClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=settings.elevenlabs_timeout_seconds)

    async def generate(self, text: str) -> bytes:
        voice_id = quote(self.settings.elevenlabs_voice_id, safe="")
        response = await self.http.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
            json={"text": text, "model_id": self.settings.elevenlabs_model_id},
        )
        response.raise_for_status()
        if not response.content or not response.headers.get("content-type", "").startswith("audio/"):
            raise ValueError("ElevenLabs returned no audio")
        return response.content

    async def close(self) -> None:
        await self.http.aclose()

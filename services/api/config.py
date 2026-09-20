from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    nemotron_base_url: str = 'https://integrate.api.nvidia.com/v1'
    nemotron_api_key: str = Field(default='', repr=False)
    nemotron_model: str = 'nvidia/nemotron-3.5-lightning-30b-a3b'
    nemotron_temperature: float = Field(default=0, ge=0, le=2)
    nemotron_max_tokens: int = Field(default=256, ge=1, le=1024)
    # Existing variable now controls inference/read time, not connection setup.
    nemotron_timeout_seconds: float = Field(default=30, gt=0, le=60)
    nemotron_connect_timeout_seconds: float = Field(default=5, gt=0, le=10)
    nemotron_write_timeout_seconds: float = Field(default=10, gt=0, le=15)
    nemotron_pool_timeout_seconds: float = Field(default=5, gt=0, le=10)
    elevenlabs_api_key: str = Field(default='', repr=False)
    elevenlabs_voice_id: str = ''
    elevenlabs_model_id: str = 'eleven_multilingual_v2'
    elevenlabs_timeout_seconds: float = Field(default=15, gt=0, le=60)
    app_env: str = 'development'
    audio_dir: Path = ROOT / 'runtime/audio'
    public_audio_path: str = '/audio'
    cors_origins: str = 'http://localhost:3000,http://localhost:5173'

    @field_validator('audio_dir')
    @classmethod
    def resolve_audio(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (ROOT / value).resolve()

    @field_validator('public_audio_path')
    @classmethod
    def local_audio_path(cls, value: str) -> str:
        import re
        if not re.fullmatch(r'/[a-zA-Z0-9_-]+', value):
            raise ValueError('PUBLIC_AUDIO_PATH must be one local path segment')
        if value in {'/api', '/src', '/health'}:
            raise ValueError('PUBLIC_AUDIO_PATH conflicts with application routes')
        return value

    @property
    def local_origins(self) -> list[str]:
        from urllib.parse import urlparse
        origins = [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
        for origin in origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError('CORS origins must be local origins without paths')
        return origins

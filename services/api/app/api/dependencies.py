from fastapi import Request

from app.adapters.fake.providers import FakeTacticClassifier, FakeVoiceProvider
from app.core.config import Settings
from app.database.memory import InMemorySessionRepository
from app.ports.providers import TacticClassifier, VoiceProvider


def build_providers(settings: Settings) -> tuple[TacticClassifier, VoiceProvider]:
    # --- Classifier ---
    if settings.use_mock_classifier:
        classifier: TacticClassifier = FakeTacticClassifier()
    else:
        from app.adapters.nemotron.provider import NemotronClassifier

        if not settings.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY must be set when USE_MOCK_CLASSIFIER=false")
        classifier = NemotronClassifier(
            api_key=settings.nvidia_api_key, model=settings.nvidia_model
        )

    # --- Voice ---
    if settings.use_mock_voice:
        voice: VoiceProvider = FakeVoiceProvider()
    else:
        from app.adapters.elevenlabs.provider import ElevenLabsVoiceProvider

        if not settings.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY must be set when USE_MOCK_VOICE=false")
        voice = ElevenLabsVoiceProvider(api_key=settings.elevenlabs_api_key)

    return classifier, voice


def get_session_repo(request: Request) -> InMemorySessionRepository:
    return request.app.state.session_repo

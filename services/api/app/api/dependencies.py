from app.adapters.fake.providers import FakeTacticClassifier, FakeVoiceProvider
from app.core.config import Settings
from app.ports.providers import TacticClassifier, VoiceProvider


def build_providers(settings: Settings) -> tuple[TacticClassifier, VoiceProvider]:
    if not settings.use_mock_classifier or not settings.use_mock_voice:
        raise ValueError("Real providers are not implemented; keep USE_MOCK_* flags true.")
    return FakeTacticClassifier(), FakeVoiceProvider()

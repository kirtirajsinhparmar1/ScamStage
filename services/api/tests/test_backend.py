import asyncio
import json
from pathlib import Path

import pytest
from app.core.config import Settings
from app.domain.enums import Action, ScenarioState
from app.main import create_app
from app.schemas.contracts import ParticipantTurn, TurnResult
from app.services.scenario_engine import ScenarioEngine
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def test_health():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_complete_scenario_and_terminal_guard():
    engine = ScenarioEngine()
    state = ScenarioState.INTRO
    for expected in (
        ScenarioState.AUTHORITY,
        ScenarioState.URGENCY,
        ScenarioState.VERIFICATION,
        ScenarioState.COMPLETED,
    ):
        state = engine.advance(state, Action.CONTINUE)
        assert state == expected
    with pytest.raises(ValueError, match="completed"):
        engine.advance(state, Action.CONTINUE)


@pytest.mark.parametrize("state", list(ScenarioState)[:-1])
def test_end_call_from_every_active_state(state):
    assert ScenarioEngine().advance(state, Action.END_CALL) == ScenarioState.COMPLETED


def test_verification_action():
    assert (
        ScenarioEngine().advance(ScenarioState.AUTHORITY, Action.REQUEST_VERIFICATION)
        == ScenarioState.VERIFICATION
    )


def test_fake_providers_are_wired_without_credentials():
    application = create_app(Settings(_env_file=None))
    result = asyncio.run(
        application.state.classifier.classify("Can I verify this?", ScenarioState.AUTHORITY)
    )
    assert result.participant_intent == "skeptical"
    assert result.detected_tactics == ["authority"]
    assert asyncio.run(application.state.voice.synthesize("Hello")) is None


def test_real_provider_flag_fails_explicitly():
    with pytest.raises(ValueError, match="NVIDIA_API_KEY must be set"):
        create_app(Settings(_env_file=None, use_mock_classifier=False))


def test_real_voice_flag_fails_without_key():
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY must be set"):
        create_app(Settings(_env_file=None, use_mock_voice=False))


def test_diagnostics_with_fake_providers():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/diagnostics/providers")
        assert response.status_code == 200
        data = response.json()
        assert data["classifier_ok"] is True
        assert data["voice_ok"] is True
        assert data["classifier_error"] is None
        assert data["voice_error"] is None
        assert data["classifier_result"]["participant_intent"] == "skeptical"


@pytest.mark.parametrize(
    "name,model", [("participant-turn", ParticipantTurn), ("turn-result", TurnResult)]
)
def test_shared_fixtures_match_python_and_json_schema(name, model):
    directory = ROOT / "packages/contracts"
    schema = json.loads((directory / f"{name}.schema.json").read_text())
    fixture = json.loads((directory / "fixtures" / f"{name}.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture)
    model.model_validate(fixture)

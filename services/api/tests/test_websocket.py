import pytest
from app.core.config import Settings
from app.domain.enums import ScenarioState
from app.main import create_app
from app.schemas.contracts import TurnResult
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def app_client():
    application = create_app(Settings(_env_file=None))
    with TestClient(application) as client:
        yield client


def test_websocket_invalid_session_rejected(app_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/api/sessions/non-existent-id/stream"):
            pass
    assert exc_info.value.code == 1008


def test_websocket_ended_session_rejected(app_client: TestClient) -> None:
    # Create and then end session
    res = app_client.post("/api/sessions")
    session_id = res.json()["id"]
    app_client.post(f"/api/sessions/{session_id}/end")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect(f"/api/sessions/{session_id}/stream"):
            pass
    assert exc_info.value.code == 1008


def test_websocket_full_turn_progression(app_client: TestClient) -> None:
    # Create session
    res = app_client.post("/api/sessions")
    session_id = res.json()["id"]

    with app_client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        # Turn 1: intro -> authority
        ws.send_json(
            {
                "type": "participant_turn",
                "text": "Hello, who is calling?",
                "input_mode": "text",
            }
        )
        data1 = ws.receive_json()
        turn1 = TurnResult.model_validate(data1)
        assert turn1.session_id == session_id
        assert turn1.speaker == "scammer"
        assert turn1.scenario_state == ScenarioState.AUTHORITY
        assert not turn1.is_complete
        assert len(turn1.available_actions) > 0

        # Turn 2: authority -> urgency
        ws.send_json(
            {
                "type": "participant_turn",
                "text": "What does this have to do with me?",
                "input_mode": "text",
            }
        )
        data2 = ws.receive_json()
        turn2 = TurnResult.model_validate(data2)
        assert turn2.scenario_state == ScenarioState.URGENCY
        assert not turn2.is_complete

        # Turn 3: urgency -> verification (skeptical trigger)
        ws.send_json(
            {
                "type": "participant_turn",
                "text": "Can I verify your credentials first?",
                "input_mode": "text",
            }
        )
        data3 = ws.receive_json()
        turn3 = TurnResult.model_validate(data3)
        assert turn3.scenario_state == ScenarioState.VERIFICATION
        assert not turn3.is_complete

        # Turn 4: verification -> completed
        ws.send_json(
            {
                "type": "participant_turn",
                "text": "I understand, thank you.",
                "input_mode": "text",
            }
        )
        data4 = ws.receive_json()
        turn4 = TurnResult.model_validate(data4)
        assert turn4.scenario_state == ScenarioState.COMPLETED
        assert turn4.is_complete
        assert turn4.available_actions == []


def test_websocket_end_call_hangup(app_client: TestClient) -> None:
    res = app_client.post("/api/sessions")
    session_id = res.json()["id"]

    with app_client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        # Participant immediately hangs up
        ws.send_json(
            {
                "type": "participant_turn",
                "text": "This sounds like a scam, I am going to hang up now. Goodbye!",
                "input_mode": "text",
            }
        )
        data = ws.receive_json()
        turn = TurnResult.model_validate(data)
        assert turn.scenario_state == ScenarioState.COMPLETED
        assert turn.is_complete
        assert "terminated" in turn.text.lower()

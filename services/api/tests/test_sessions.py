from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_create_session() -> None:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "active"
    assert data["scenario_state"] == "intro"


def test_end_session() -> None:
    # First create a session
    create_response = client.post("/api/sessions")
    session_id = create_response.json()["id"]

    # End the session
    end_response = client.post(f"/api/sessions/{session_id}/end")
    assert end_response.status_code == 200
    data = end_response.json()
    assert data["id"] == session_id
    assert data["status"] == "ended"
    assert data["scenario_state"] == "completed"


def test_end_session_not_found() -> None:
    response = client.post("/api/sessions/invalid-id/end")
    assert response.status_code == 404

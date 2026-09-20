"""Exercise the running real application; no provider mocks."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.contracts.classification import ParticipantClassification
from packages.contracts.response import EndCallResponse, SessionResponse, TurnResponse


ACTIVE_STAGES = {"authority", "urgency", "verification_resistance", "action_request"}
DEMO_RESPONSES = [
    "What exactly is this alert about?",
    "How do I know you are really from the credit union?",
    "I am uncomfortable continuing this conversation.",
    "I will call the number on my card instead.",
    "I am just going to hang up.",
]
LIVE_RESPONSES = [
    "What exactly is this alert about?",
    "How do I know you are really from the credit union?",
    "I am uncomfortable continuing this conversation.",
    "Can you explain what you mean in general terms?",
    "Can you explain this alert one more time?",
]


def check_audio(client: httpx.Client, payload: dict, require_live: bool) -> None:
    url = payload["audio_url"]
    if url is None:
        assert payload["voice_fallback"] is True, "Missing audio must declare fallback"
        assert not require_live, "Live ElevenLabs audio was required"
        return
    assert url.startswith("/") and not url.startswith("//") and ".." not in url
    response = client.get(url)
    response.raise_for_status()
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) > 100, "Audio was unexpectedly empty"
    assert payload["voice_fallback"] is False


def explicit_retry(client: httpx.Client, session_id: str) -> dict:
    """Model the visible Retry caller response button exactly once."""
    retry = client.post(f"/api/sessions/{session_id}/dialogue/retry", json={})
    retry.raise_for_status()
    return retry.json()


def check_live_providers(client: httpx.Client) -> None:
    """Five live voice-mode turns, followed by the explicit end-call action."""
    scenario_id = "fictional_bank_fraud_v1"
    created = client.post(
        "/api/sessions",
        json={"scenario_id": scenario_id, "interaction_mode": "voice"},
    )
    created.raise_for_status()
    session = created.json()
    validated_session = SessionResponse.model_validate(session)
    assert validated_session.scenario_id == scenario_id
    assert validated_session.interaction_mode == "voice"
    assert validated_session.call_active is True
    retries = 0
    if validated_session.retry_available:
        session = explicit_retry(client, session["session_id"])
        validated_session = SessionResponse.model_validate(session)
        retries += 1
    assert validated_session.retry_available is False
    assert validated_session.dialogue_provider == "ollama"
    assert validated_session.dialogue_fallback is False
    check_audio(client, session, require_live=True)
    providers = []
    started = time.monotonic()
    for index, text in enumerate(LIVE_RESPONSES, start=1):
        response = client.post(
            f"/api/sessions/{session['session_id']}/turns",
            json={"participant_text": text, "input_mode": "voice"},
        )
        if response.status_code == 503:
            error = response.json()
            assert error["retry_available"] is True
            response = client.post(
                f"/api/sessions/{session['session_id']}/dialogue/retry", json={})
            retries += 1
        response.raise_for_status()
        turn = response.json()
        validated = TurnResponse.model_validate(turn)
        assert validated.analysis.evidence_span in text
        assert validated.classifier_provider == "fast_safety_policy"
        assert validated.classifier_fallback is False
        assert validated.classifier_attempted is False
        assert validated.dialogue_provider == "ollama"
        assert validated.dialogue_fallback is False
        assert validated.voice_provider == "elevenlabs", "Genuine ElevenLabs audio required"
        assert validated.voice_fallback is False, "Genuine ElevenLabs audio required"
        assert validated.audio_url, "Live audio URL required"
        assert validated.completed is False, f"Turn {index} unexpectedly ended the call"
        assert validated.debrief is None
        assert validated.stage_after in ACTIVE_STAGES
        check_audio(client, turn, require_live=True)
        providers.append({
            "turn": index,
            "dialogue_provider": validated.dialogue_provider,
            "voice_provider": validated.voice_provider,
            "classifier_provider": validated.classifier_provider,
            "completed": validated.completed,
        })

    saved = client.get(f"/api/sessions/{session['session_id']}")
    saved.raise_for_status()
    state = saved.json()
    assert state["turn_count"] == 5 and len(state["history"]) == 5
    assert state["call_active"] is True and state["completed"] is False
    assert len(state["timeline"]) == 5
    ended_response = client.post(f"/api/sessions/{session['session_id']}/end")
    ended_response.raise_for_status()
    ended = EndCallResponse.model_validate(ended_response.json())
    assert ended.completed is True and ended.call_active is False
    assert ended.completion_reason == "user_ended_call"
    assert ended.debrief.outcome == "user_ended_call"
    assert ended.debrief.training_risk_score == ended.risk_score
    assert len(ended.timeline) == 6 and ended.timeline[-1]["event"] == "call_ended"
    final_state = client.get(f"/api/sessions/{session['session_id']}")
    final_state.raise_for_status()
    assert final_state.json()["completed"] is True
    print(json.dumps({
        "result": "PASS", "scenario_id": scenario_id,
        "non_terminal_ollama_turns": len(providers),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "opening_dialogue_provider": validated_session.dialogue_provider,
        "opening_voice_provider": "elevenlabs",
        "explicit_retries": retries,
        "turns": providers,
        "end_call_debrief": ended.debrief.outcome,
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--all-scenarios", action="store_true", help="Also exercise safe and risky paths for every catalog scenario")
    args = parser.parse_args()
    if args.require_live and args.all_scenarios:
        parser.error("--require-live is the five-turn live call check; run --all-scenarios against the deterministic fallback server")
    # Covers the adapter's maximum two-attempt budget plus voice synthesis.
    with httpx.Client(base_url=args.base_url, timeout=260 if args.require_live else 100) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        if args.require_live:
            check_live_providers(client)
            return
        created = client.post("/api/sessions", json={})
        created.raise_for_status()
        session = created.json()
        assert session["stage"] == "authority"
        assert session["scammer_text"] and session["simulation_notice"]
        assert session["call_active"] is True and session["retry_available"] is False
        check_audio(client, session, args.require_live)
        previous = session["stage"]
        providers = []
        for text in DEMO_RESPONSES:
            response = client.post(
                f"/api/sessions/{session['session_id']}/turns",
                json={"participant_text": text},
            )
            response.raise_for_status()
            turn = response.json()
            analysis = ParticipantClassification.model_validate(turn["analysis"])
            assert analysis.evidence_span in text
            assert turn["stage_before"] == previous
            assert turn["stage_after"] in ACTIVE_STAGES, turn["stage_after"]
            assert turn["scammer_text"] and turn["tactics_triggered"]
            assert turn["completed"] is False and turn["debrief"] is None
            assert 0 <= turn["risk_score"] <= 1
            assert turn["classifier_provider"] == "fast_safety_policy"
            assert turn["classifier_fallback"] is False
            check_audio(client, turn, args.require_live)
            previous = turn["stage_after"]
            providers.append({key: turn[key] for key in (
                "classifier_provider", "dialogue_provider", "voice_provider",
                "classifier_fallback", "dialogue_fallback", "voice_fallback",
            )})
        saved = client.get(f"/api/sessions/{session['session_id']}")
        saved.raise_for_status()
        state = saved.json()
        assert state["turn_count"] == 5 and len(state["history"]) == 5
        assert state["stage"] == previous
        assert state["call_active"] is True and state["completed"] is False
        ended = client.post(f"/api/sessions/{session['session_id']}/end")
        ended.raise_for_status()
        ended_model = EndCallResponse.model_validate(ended.json())
        assert ended_model.debrief.outcome == "user_ended_call"
        assert ended_model.completed is True and ended_model.call_active is False
        if args.all_scenarios:
            catalog = client.get('/api/scenarios')
            catalog.raise_for_status()
            assert len(catalog.json()) == 3
            for scenario in catalog.json():
                response = client.post('/api/sessions', json={'scenario_id': scenario['id']})
                response.raise_for_status()
                started = response.json()
                assert started['scenario_id'] == scenario['id']
                assert started['scenario_name'] == scenario['display_name']
                check_audio(client, started, args.require_live)
                for text in DEMO_RESPONSES[:2]:
                    response = client.post(f"/api/sessions/{started['session_id']}/turns", json={'participant_text': text})
                    response.raise_for_status()
                    result = response.json()
                    assert result['completed'] is False and result['debrief'] is None
                    assert result['stage_after'] in ACTIVE_STAGES
                    assert result['analysis']['evidence_span'] in text
                    check_audio(client, result, args.require_live)
                ended = client.post(f"/api/sessions/{started['session_id']}/end")
                ended.raise_for_status()
                result = ended.json()
                assert result['completed'] and not result['call_active']
                assert result['debrief']['outcome'] == 'user_ended_call'
                assert result['debrief']['scenario_name'] == scenario['display_name']
                detail = client.get(f"/api/sessions/{started['session_id']}").json()
                assert detail['timeline'][-1]['event'] == 'call_ended'
                assert client.post(f"/api/sessions/{started['session_id']}/turns", json={'participant_text': 'Hmm'}).status_code == 409
                print(f"PASS: {scenario['id']} rolling turns, explicit end, timeline, debrief, audio/provider contract", flush=True)
        print(json.dumps({"result": "PASS", "health": health.json(), "turns": providers}, indent=2))


if __name__ == "__main__":
    main()

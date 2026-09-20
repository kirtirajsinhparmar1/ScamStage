"""Exercise the running real application; no provider mocks."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.contracts.classification import ParticipantClassification
from packages.contracts.response import TurnResponse


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


def check_live_providers(client: httpx.Client) -> None:
    """One live classification, not a probabilistic scenario-branch matrix."""
    scenario_id = "fictional_job_recruiter_v1"
    created = client.post("/api/sessions", json={"scenario_id": scenario_id})
    created.raise_for_status()
    session = created.json()
    assert session["scenario_id"] == scenario_id
    check_audio(client, session, require_live=True)
    text = "I am hanging up."
    started = time.monotonic()
    response = client.post(
        f"/api/sessions/{session['session_id']}/turns",
        json={"participant_text": text},
    )
    response.raise_for_status()
    turn = response.json()
    validated = TurnResponse.model_validate(turn)
    print(json.dumps({
        "result": "OBSERVED", "elapsed_seconds": round(time.monotonic() - started, 2),
        "classifier_provider": validated.classifier_provider,
        "classifier_fallback": validated.classifier_fallback,
        "classifier_fallback_reason": turn.get("classifier_fallback_reason"),
        "voice_provider": validated.voice_provider,
        "voice_fallback": validated.voice_fallback,
        "audio_url_present": bool(validated.audio_url),
    }), flush=True)
    assert validated.analysis.evidence_span in text
    assert validated.classifier_provider == "nemotron", "Genuine Nemotron result required"
    assert validated.classifier_fallback is False, "Live Nemotron must not fall back"
    assert validated.voice_provider == "elevenlabs", "Genuine ElevenLabs audio required"
    assert validated.voice_fallback is False, "Live ElevenLabs must not fall back"
    assert validated.audio_url, "Live audio URL required"
    assert turn["stage_before"] == session["stage"]
    assert turn["risk_before"] == session["risk_score"]
    check_audio(client, turn, require_live=True)
    saved = client.get(f"/api/sessions/{session['session_id']}")
    saved.raise_for_status()
    state = saved.json()
    assert state["turn_count"] == 1 and len(state["history"]) == 1
    assert state["stage"] == turn["stage_after"]
    print(json.dumps({
        "result": "PASS", "scenario_id": scenario_id, "classification_requests": 1,
        "classifier_provider": turn["classifier_provider"],
        "classifier_fallback": turn["classifier_fallback"],
        "voice_provider": turn["voice_provider"],
        "voice_fallback": turn["voice_fallback"],
        "audio_url_present": bool(turn["audio_url"]),
        "audio_retrieved": True,
        "live_classification_returned": True,
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--all-scenarios", action="store_true", help="Also exercise safe and risky paths for every catalog scenario")
    args = parser.parse_args()
    if args.require_live and args.all_scenarios:
        parser.error("--require-live is a one-turn provider check; run --all-scenarios against the deterministic fallback server")
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
        check_audio(client, session, args.require_live)
        previous = session["stage"]
        providers = []
        for text, expected_stage in [
            ("I will call the number on my card instead.", "verification_resistance"),
            ("I will follow those instructions.", "action_request"),
        ]:
            response = client.post(
                f"/api/sessions/{session['session_id']}/turns",
                json={"participant_text": text},
            )
            response.raise_for_status()
            turn = response.json()
            analysis = ParticipantClassification.model_validate(turn["analysis"])
            assert analysis.evidence_span in text
            assert turn["stage_before"] == previous
            assert turn["stage_after"] == expected_stage, turn["stage_after"]
            assert turn["scammer_text"] and turn["tactics_triggered"]
            assert 0 <= turn["risk_score"] <= 1
            assert turn["classifier_provider"] in {"nemotron", "fallback"}
            assert turn["classifier_fallback"] == (turn["classifier_provider"] == "fallback")
            if args.require_live:
                assert not turn["classifier_fallback"], "Live Nemotron was required"
            check_audio(client, turn, args.require_live)
            previous = turn["stage_after"]
            providers.append({key: turn[key] for key in (
                "classifier_provider", "voice_provider", "classifier_fallback", "voice_fallback"
            )})
        saved = client.get(f"/api/sessions/{session['session_id']}")
        saved.raise_for_status()
        state = saved.json()
        assert state["turn_count"] == 2 and len(state["history"]) == 2
        assert state["stage"] == previous
        if args.all_scenarios:
            catalog = client.get('/api/scenarios')
            catalog.raise_for_status()
            assert len(catalog.json()) == 3
            for scenario in catalog.json():
                for responses, outcome in [
                    (["I am hanging up."], 'safe_exit'),
                    (["I will follow those instructions.", "I will follow those instructions."], 'risky_outcome'),
                ]:
                    response = client.post('/api/sessions', json={'scenario_id': scenario['id']})
                    response.raise_for_status()
                    started = response.json()
                    assert started['scenario_id'] == scenario['id']
                    assert started['scenario_name'] == scenario['display_name']
                    check_audio(client, started, args.require_live)
                    risk = started['risk_score']
                    for text in responses:
                        response = client.post(f"/api/sessions/{started['session_id']}/turns", json={'participant_text': text})
                        response.raise_for_status()
                        result = response.json()
                        assert result['risk_before'] == risk
                        risk = result['risk_score']
                        assert result['analysis']['evidence_span'] in text
                        if args.require_live:
                            assert not result['classifier_fallback'], 'Live Nemotron was required'
                        check_audio(client, result, args.require_live)
                    assert result['stage_after'] == outcome and result['completed']
                    assert result['debrief']['outcome'] == outcome
                    assert result['debrief']['scenario_name'] == scenario['display_name']
                    detail = client.get(f"/api/sessions/{started['session_id']}").json()
                    assert detail['timeline'][-1]['risk_after'] == risk
                    assert detail['debrief'] == result['debrief']
                    assert client.post(f"/api/sessions/{started['session_id']}/turns", json={'participant_text': 'Hmm'}).status_code == 409
                print(f"PASS: {scenario['id']} safe/risky branches, timeline, debrief, audio/provider contract", flush=True)
        print(json.dumps({"result": "PASS", "health": health.json(), "turns": providers}, indent=2))


if __name__ == "__main__":
    main()

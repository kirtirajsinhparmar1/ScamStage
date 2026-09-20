# Backend WebSocket Streaming Handoff

Implemented: `WS /api/sessions/{session_id}/stream`, interactive multi-turn simulation loop,
scenario dialog responder, and session state tracking.

## Features
- **Streaming endpoint**: `WS /api/sessions/{session_id}/stream`
- Validates session existence and active status (rejects with WebSocket code 1008 if invalid/ended).
- Accepts `ParticipantTurn` JSON messages (`text`, `input_mode`).
- Calls configured classifier (`FakeTacticClassifier` or `NemotronClassifier`) to detect intent and tactics.
- Evaluates participant actions (`CONTINUE`, `REQUEST_VERIFICATION`, or `END_CALL`).
- Advances scenario state via `ScenarioEngine` (`INTRO` -> `AUTHORITY` -> `URGENCY` -> `VERIFICATION` -> `COMPLETED`).
- Produces scenario-appropriate scammer dialog turns via `ScenarioDialogResponder`.
- Integrates voice synthesis provider (`FakeVoiceProvider` or `ElevenLabsVoiceProvider`).
- Emits `TurnResult` JSON messages matching shared contract schema.
- Tracks turn history and updates session state in `InMemorySessionRepository`.
- Gracefully terminates with WebSocket code 1000 when scenario is completed or participant ends call.

## Validation
- 20 pytest unit tests passing.
- Ruff linting and formatting clean.
- Shared JSON Schema contract drift checks passed.

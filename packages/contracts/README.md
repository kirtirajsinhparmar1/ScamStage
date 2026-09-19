# Shared contracts v0.1
Person 2 owns changes; coordinate breaking changes with both teammates.
Python models in `services/api/app/schemas/contracts.py` are the source of truth.
Run `make contracts` after changing them; commit schemas and fixtures together.
`make check` detects schema drift and validates fixtures.

Frontend: use `fixtures/turn-result.json` as a mock. `audio_url: null` means text-only.
`scenario_state` and `risk_level` are the agreed field names. Risk ranges from 0 to 1.
These turn contracts are drafts for the future WebSocket endpoint, not a live API yet.

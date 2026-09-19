# Backend foundation handoff
Implemented: GET /api/health, generated draft turn contracts, fixture JSON,
fake classifier/voice interfaces and wiring, pure scenario transitions, tests and CI.

Person 1: build UI against contract fixtures under apps/web.
Person 3: implement provider protocols under app/adapters; keep fakes working.
Person 2 next: session create/end operations and an in-memory session repository,
then one WebSocket turn using fake providers, before adding PostgreSQL.

Session REST routes, WebSockets, debriefs, real AI/voice/STT and persistence are not implemented.
The fake risk score is fixed fixture data and must not be used as a real assessment.

Validation at setup: Python 3.14.3; 11 pytest tests passed; Ruff lint and formatting
passed; generated contract drift checks passed; live HTTP health returned {"status":"ok"}.
Two upstream TestClient deprecation warnings remain; tests succeed.
Docker/Compose could not be exercised because Docker is not installed on this machine.

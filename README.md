# SCAMSTAGE

A three-person scam-awareness simulator. This repository is the first backend checkpoint.
Only `GET /api/health` is live; frontend, session endpoints, database and real providers are future work.

## Start locally

Prerequisites: Python 3.12–3.14, Git, Make, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
This checkpoint is tested with Python 3.14. Install uv with `python3 -m pip install uv==0.12.17` if needed.
From this directory:

```sh
make setup
make check
make run
```

Open http://localhost:8000/api/health → `{"status":"ok"}`.
Interactive API docs: http://localhost:8000/docs. Stop the server with Ctrl+C.
`make setup` installs locked dependencies and creates `.env` only if absent.
No API keys or database are needed. Keep both `USE_MOCK_*` flags true.

If uv is not on PATH in the original Codex workspace, use the already-installed local copy:

```sh
make UV=../../work/tooling/bin/uv setup check
make UV=../../work/tooling/bin/uv run
```

## Structure and ownership

```text
apps/web/                    Person 1: frontend placeholder and handoff
services/api/app/
  main.py                    Person 2: FastAPI app factory
  api/routes/health.py        Live health endpoint
  api/dependencies.py         Provider construction
  core/                      Environment configuration
  domain/                    Scenario state and action enums
  schemas/                   Pydantic contract source of truth
  services/                  Pure scenario transition engine
  ports/                     Classifier and voice interfaces
  adapters/fake/             Runnable deterministic providers
  adapters/nemotron/         Person 3: implementation placeholder
  adapters/elevenlabs/        Person 3: implementation placeholder
  database/                  Person 2: persistence placeholder
  scenarios/                 Person 2: future scenario definitions
services/api/tests/          Health, transition, provider and contract tests
packages/contracts/          Generated JSON Schema and frontend fixtures
scripts/                     Contract exporter and drift check
data/                        Person 3: future synthetic/evaluation data
infra/                       Person 3: deployment handoff
docs/handoffs/               Tested checkpoint notes
.github/                    Backend CI and PR template
```

The root `pyproject.toml` and `uv.lock` manage the backend environment.
Routes will call application services; services use ports; adapters implement those ports.
The engine is a skeleton, not a complete conversation loop. A completed state cannot advance.
The classifier returns fixture data and fake voice returns `None` for text-only mode.

## Contracts and tests

Change Python models first, run `make contracts`, then update fixtures and commit all together.
`make check` runs lint/format checks, checks generated schema drift, and runs pytest.
Person 1 can start with the JSON fixtures before the session API exists.
The planned API is:

| Route | Status |
| --- | --- |
| GET /api/health | Implemented |
| POST /api/sessions | Implemented |
| POST /api/sessions/{id}/end | Implemented |
| GET /api/diagnostics/providers | Implemented |
| WS /api/sessions/{id}/stream | Implemented |
| GET /api/sessions/{id}/debrief | Planned |

Tests use FastAPI's [TestClient](https://fastapi.tiangolo.com/tutorial/testing/).
Dependencies use uv's [locked sync workflow](https://docs.astral.sh/uv/concepts/projects/sync/).

## Docker option

Install/start Docker Desktop, then run `make up`. The same health URL is available.
`make down` stops the service. Compose intentionally starts only the API at this milestone.
Docker is not required for the local Python workflow.

## Git collaboration

See [docs/git-workflow.md](docs/git-workflow.md) for the initial GitHub push and PR flow.
Each teammate starts from tested `dev`, uses a feature branch, and leaves handoff notes.
Coordinate changes to shared contracts with Person 2 before merging.

Next for Person 2: implement session create/end with in-memory storage, then a single
WebSocket turn using fake providers. Add PostgreSQL and real providers after that works.

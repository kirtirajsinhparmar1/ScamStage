UV ?= uv
.PHONY: setup run test lint check contracts contracts-check up down
setup:
	$(UV) sync --locked
	@test -f .env || cp .env.example .env
run:
	$(UV) run --locked uvicorn app.main:app --app-dir services/api --reload --host 127.0.0.1 --port 8000
test:
	$(UV) run --locked pytest -q
lint:
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
contracts:
	$(UV) run --locked python scripts/export_contracts.py
contracts-check:
	$(UV) run --locked python scripts/export_contracts.py --check
check: lint contracts-check test
up:
	docker compose up --build -d
down:
	docker compose down

.PHONY: install test lint migrate serve worker compose-config compose-up

install:
	python3 -m venv .venv
	.venv/bin/pip install -e '.[dev]'

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests

migrate:
	.venv/bin/alembic upgrade head

serve:
	.venv/bin/uvicorn reachpath.api:app --app-dir src --host 127.0.0.1 --port 8020

worker:
	.venv/bin/reachpath worker

compose-config:
	docker compose config

compose-up:
	docker compose up -d --build

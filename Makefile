.PHONY: install lint test run up down migrate consumer

install:
	python -m pip install -e '.[dev]'

lint:
	ruff check .
	ruff format --check .

test:
	pytest -q

run:
	uvicorn app.main:app --reload

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

consumer:
	python -m app.kafka.consumer


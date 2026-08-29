.PHONY: up down logs test lint build

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

test:
	pytest

lint:
	ruff check src tests

build:
	docker compose build

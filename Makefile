
.PHONY: start stop logs lint format format_diff router-tests

PYTEST_ARGS ?=

pull:
	bash docker/pull_image.sh python:3.12-slim
	bash docker/pull_image.sh node:20-slim
	bash docker/pull_image.sh node:20-alpine
	bash docker/pull_image.sh milvusdb/milvus:v2.5.6
	bash docker/pull_image.sh neo4j:5.26
	bash docker/pull_image.sh minio/minio:RELEASE.2023-03-20T20-16-18Z
	bash docker/pull_image.sh ghcr.io/astral-sh/uv:0.7.2
	bash docker/pull_image.sh nginx:alpine
	bash docker/pull_image.sh quay.io/coreos/etcd:v3.5.5

start:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found. Please create it from .env.template"; \
		exit 1; \
	fi
	docker compose up -d

stop:
	docker compose down

logs:
	@docker logs --tail=50 api-dev
	@echo "\n\nBranch: $$(git branch --show-current)"
	@echo "Commit ID: $$(git rev-parse HEAD)"
	@echo "System: $$(uname -a)"

######################
# LINTING AND FORMATTING
######################

lint:
	uv run python -m ruff check .
	uv run python -m ruff format --check src
	uv run python -m ruff check --select I src

format:
	uv run python -m ruff format .
	uv run python -m ruff check . --fix
	uv run python -m ruff check --select I src --fix
	cd web && npm run format

router-tests:
	docker compose exec -T api uv run --group test pytest test/api $(PYTEST_ARGS)


.PHONY: start stop logs lint format format_diff router-tests

PYTEST_ARGS ?=

start:
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
	uv run python -m ruff format src --diff
	uv run python -m ruff check --select I src

format:
	uv run ruff format .
	uv run ruff check . --fix
	uv run python -m ruff check --select I src --fix

format_diff:
	uv run ruff format --diff .

router-tests:
	docker compose exec -T api uv run --group test pytest test/api $(PYTEST_ARGS)

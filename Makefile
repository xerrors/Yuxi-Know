
.PHONY: start logs

start:
	docker compose up -d

stop:
	docker compose down

logs:
	@docker logs --tail=50 api-dev
	@echo "Commit ID: $$(git rev-parse HEAD)"
	@echo "System: $$(uname -a)"

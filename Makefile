.PHONY: up down dev build migrate seed logs clean ps test-backend verify

# ─── Docker Compose ──────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

dev: up
	@echo "InsightAI running at http://localhost:3000"
	@echo "API docs at http://localhost:8000/api/docs"
	@echo "MinIO console at http://localhost:9001"
	@echo "Cube playground at http://localhost:4000"

# ─── Tests / Verification ─────────────────────────────────────────────────────
test-backend:
	docker compose exec backend pytest -q

verify: test-backend
	docker compose exec frontend npx tsc --noEmit
	@echo "verify OK"

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

clean:
	docker compose down -v --remove-orphans

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

migrate-down:
	docker compose exec backend alembic downgrade -1

migration:
	docker compose exec backend alembic revision --autogenerate -m "$(name)"

seed:
	docker compose exec backend python seed.py

# ─── Backend ──────────────────────────────────────────────────────────────────
backend-shell:
	docker compose exec backend bash

backend-lint:
	docker compose exec backend ruff check app/ --fix && ruff format app/

# ─── Frontend ─────────────────────────────────────────────────────────────────
frontend-shell:
	docker compose exec frontend sh

frontend-lint:
	docker compose exec frontend npx biome check --apply .

frontend-install:
	docker compose exec frontend npm install

# ─── Init (first run) ─────────────────────────────────────────────────────────
init: build up
	@echo "Waiting for postgres..."
	@sleep 5
	$(MAKE) migrate
	$(MAKE) seed
	@echo ""
	@echo "InsightAI initialized!"
	@echo "Admin: admin@insightai.local / Admin@123456"
	@echo "User:  demo@insightai.local  / Demo@123456"

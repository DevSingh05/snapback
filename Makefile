.PHONY: setup lint format test hygiene check api web sidecar

setup: ## install python and node dependencies
	uv sync
	npm install

lint: ## check style, types and formatting without changing files
	uv run ruff check .
	uv run ruff format --check .
	npm run lint
	npm run format:check
	npm run typecheck

format: ## fix style and formatting in place
	uv run ruff check --fix .
	uv run ruff format .
	npm run format

test: ## run the python tests
	uv run pytest
	npm run test -w apps/web

hygiene: ## fail if sponsor data, secrets or large files are tracked
	bash scripts/check_repo_hygiene.sh

check: hygiene lint test ## everything CI runs; must pass before a PR merges

api: ## run the API on :8000
	uv run uvicorn snapback.api.main:app --reload --port 8000

web: ## run the web app on :5173 (proxies /api to :8000)
	npm run dev -w apps/web

sidecar: ## run the intake sidecar stub
	npm run dev -w apps/sidecar

.PHONY: setup lint format test hygiene check api web sidecar purge eval eval-baseline prefetch-weights eval-locate-real

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
	npm run test -w apps/sidecar

hygiene: ## fail if sponsor data, secrets or large files are tracked
	bash scripts/check_repo_hygiene.sh

check: hygiene lint test ## everything CI runs; must pass before a PR merges

api: ## run the API on :8000
	uv run uvicorn snapback.api.main:app --reload --port 8000 --no-proxy-headers

web: ## run the web app on :5173 against the API on :8000 via the /api proxy (LIVE chips)
	VITE_API_URL=/api npm run dev -w apps/web

sidecar: ## run the intake sidecar stub
	npm run dev -w apps/sidecar

purge: ## delete everything under data/ (sponsor caches, memory DB); sponsor terms: by Sun 16:00
	uv run python -m snapback.safety purge

eval: ## eval harness: writes eval/results.csv (aggregate numbers only) and runs the gate
	uv run python -m snapback.eval --baseline eval/baseline.csv

eval-baseline: ## rescore without the regression gate, then freeze it as the baseline (deliberate)
	uv run python -m snapback.eval
	cp eval/results.csv eval/baseline.csv

eval-locate-real: ## A8: locate accuracy on the kit's own photos; writes totals to eval/locate_real.csv
	uv run python -m snapback.agent.locate_eval

prefetch-weights: ## download and sha256-check the DISK, LightGlue and DINOv2 weights (vision extra)
	uv run python -m snapback.vision.locate.weights

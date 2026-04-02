.PHONY: help dev up down test lint typecheck build clean install

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies (dev + runtime)
	pip install -e ".[dev]"

dev:  ## Start backend + frontend locally (two terminals)
	@echo "Starting backend on :8000 ..."
	python -m uvicorn server.app:app --reload --port 8000 &
	@echo "Starting frontend on :3000 ..."
	cd ui && python -m http.server 3000

up:  ## Start full stack via Docker Compose
	docker compose up --build

down:  ## Stop Docker Compose stack
	docker compose down

test:  ## Run full test suite with coverage
	pytest tests/ -v --cov=core --cov=agents --cov=server --cov-report=term-missing --cov-fail-under=70

test-p0p1:  ## Run P0+P1 validation tests
	python scripts/test_p0_p1.py

test-p2:  ## Run P2 validation tests
	python scripts/test_p2.py

test-v2:  ## Run V2 improvement validation tests
	python scripts/test_v2.py

lint:  ## Run ruff linter
	ruff check . --fix

format:  ## Format code with ruff
	ruff format .

typecheck:  ## Run mypy type checker
	mypy core/ agents/ server/ --ignore-missing-imports

security:  ## Run bandit security scan
	bandit -r core/ agents/ server/ -ll

check: lint typecheck security  ## Run all quality checks

benchmark:  ## Run platform benchmarks
	python benchmarks/run_benchmarks.py

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true

build:  ## Build Docker image only
	docker build -t autonomous-engineer:latest .

logs:  ## Tail Docker Compose logs
	docker compose logs -f

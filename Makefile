.PHONY: help install dev test lint typecheck format run docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $$(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install

test: ## Run all tests
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=q_guardian --cov-report=html --cov-report=term

lint: ## Run linter
	ruff check src/ tests/

format: ## Format code
	ruff format src/ tests/

typecheck: ## Run type checker
	mypy src/q_guardian/

run: ## Run the application locally
	uvicorn src.q_guardian.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

docker-up: ## Start Docker services
	docker-compose up -d

docker-down: ## Stop Docker services
	docker-compose down

docker-build: ## Build Docker images
	docker-compose build

build: ## Build wheel and sdist
	python -m build

package-validate: ## Validate package
	python -m scripts.packaging.validate

benchmark: ## Run benchmarks (smoke)
	python -m scripts.benchmarks.run_benchmarks --iterations 10

loadtest-quick: ## Run quick load test (100 sessions)
	python -m scripts.loadtest.run_loadtest --profile quick

profile-snapshot: ## Take memory snapshot
	python -m scripts.profile.run_profiler snapshot

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage coverage.xml

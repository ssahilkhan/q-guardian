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

clean: ## Clean up generated files (cross-platform)
	@python -c "import pathlib, shutil; root = pathlib.Path('.'); dirs = [p for pat in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov') for p in root.rglob(pat)]; [shutil.rmtree(p, ignore_errors=True) for p in dirs]; [p.unlink() for p in root.rglob('*.pyc') if p.is_file()]; [pathlib.Path(n).unlink(missing_ok=True) for n in ('.coverage', 'coverage.xml')]"

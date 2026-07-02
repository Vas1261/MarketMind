# Makefile
#
# Common developer commands.
# Run `make help` to see all available targets.
#
# Convention: targets are grouped by category.
# Each target has a comment that appears in `make help`.

.PHONY: help install install-all lint format typecheck test test-unit \
        test-integration test-property test-all coverage clean \
        docker-build docker-run info

# Detect Python
PYTHON := python3
PIP    := pip

# Default target
.DEFAULT_GOAL := help

# -----------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------

help: ## Show this help message
	@echo "MarketMind — Available make targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	    | sort \
	    | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# -----------------------------------------------------------------------
# Installation
# -----------------------------------------------------------------------

install: ## Install project with dev dependencies (standard setup)
	$(PIP) install -e ".[dev]"
	pre-commit install
	@echo "✓ MarketMind development environment ready."

install-all: ## Install all optional dependencies including ML and dashboard
	$(PIP) install -e ".[all]"
	pre-commit install
	@echo "✓ Full MarketMind environment ready."

# -----------------------------------------------------------------------
# Code Quality
# -----------------------------------------------------------------------

lint: ## Run Ruff linter
	ruff check .

format: ## Format code with Ruff formatter
	ruff format .

format-check: ## Check formatting without writing changes (used in CI)
	ruff format --check .

typecheck: ## Run MyPy type checker
	mypy marketmind --config-file pyproject.toml

import-check: ## Verify module dependency rules (enforced by import-linter)
	lint-imports

quality: lint typecheck import-check ## Run all static analysis checks

# -----------------------------------------------------------------------
# Testing
# -----------------------------------------------------------------------

test-unit: ## Run unit tests only (fast, no I/O)
	MM_ENVIRONMENT=test pytest tests/unit -v -m "not slow"

test-integration: ## Run integration tests
	MM_ENVIRONMENT=test pytest tests/integration -v

test-property: ## Run property-based tests (Hypothesis)
	MM_ENVIRONMENT=test pytest tests/property -v --hypothesis-seed=42

test: ## Run unit + integration + property tests
	MM_ENVIRONMENT=test pytest tests/unit tests/integration tests/property -v

test-all: ## Run the full test suite including slow tests
	MM_ENVIRONMENT=test pytest tests/ -v

coverage: ## Run tests with coverage report
	MM_ENVIRONMENT=test pytest tests/ \
	    --cov=marketmind \
	    --cov-report=term-missing \
	    --cov-report=html:htmlcov \
	    --cov-fail-under=80
	@echo "✓ Coverage report written to htmlcov/"

# -----------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------

info: ## Show platform info (version, active config)
	MM_ENVIRONMENT=local marketmind info

config-show: ## Print the active configuration
	MM_ENVIRONMENT=local marketmind config show

config-validate: ## Validate the active configuration
	MM_ENVIRONMENT=local marketmind config validate

# -----------------------------------------------------------------------
# Docker
# -----------------------------------------------------------------------

docker-build: ## Build the development Docker image
	docker build -t marketmind:dev .

docker-run: ## Run an interactive shell in the Docker container
	docker run --rm -it \
	    -v $(PWD):/app \
	    -e MM_ENVIRONMENT=local \
	    marketmind:dev bash

docker-test: ## Run the test suite inside Docker
	docker run --rm \
	    -v $(PWD):/app \
	    -e MM_ENVIRONMENT=test \
	    marketmind:dev \
	    pytest tests/ -v

# -----------------------------------------------------------------------
# Maintenance
# -----------------------------------------------------------------------

clean: ## Remove build artifacts, caches, and temporary files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "coverage.xml" -delete 2>/dev/null || true
	@echo "✓ Cleaned."

pre-commit-run: ## Run all pre-commit hooks on all files
	pre-commit run --all-files

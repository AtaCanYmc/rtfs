.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= .venv/bin/python
RUFF ?= .venv/bin/ruff
PYTEST ?= .venv/bin/pytest
RTFS ?= .venv/bin/rtfs
UV ?= uv

CACHE_DIR ?= $(HOME)/.cache/rtfs
MCP_HOST ?= 127.0.0.1
MCP_PORT ?= 8000

.PHONY: help venv install install-redis install-mcp install-all \
        lint format format-check test test-fast check \
        mcp-stdio mcp-sse cache-clear build clean

help: ## Display available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

venv: ## Create local Python virtual environment (.venv)
	@test -d .venv || $(UV) venv

install: venv ## Install rtfs in editable mode with dev dependencies
	$(UV) pip install -e ".[dev]" --python $(PYTHON)

install-redis: venv ## Install rtfs with Redis cache extra and dev dependencies
	$(UV) pip install -e ".[redis,dev]" --python $(PYTHON)

install-mcp: venv ## Install rtfs with FastMCP server extra and dev dependencies
	$(UV) pip install -e ".[mcp,dev]" --python $(PYTHON)

install-all: venv ## Install rtfs with all optional extras (redis, mcp, dev)
	$(UV) pip install -e ".[all,dev]" --python $(PYTHON)

lint: ## Run Ruff linter across the repository
	$(RUFF) check .

format: ## Auto-fix lint issues and format code with Ruff
	$(RUFF) check --fix .
	$(RUFF) format .

format-check: ## Check code formatting without modifying files
	$(RUFF) format --check .

test: ## Run full pytest suite with verbose output
	$(PYTEST) -v

test-fast: ## Run pytest suite stopping on first failure
	$(PYTEST) -x -q

check: lint test ## Run all quality gates (ruff check + pytest)

mcp-stdio: ## Run the FastMCP server over stdio transport
	$(RTFS) mcp --transport stdio

mcp-sse: ## Run the FastMCP server over SSE transport (MCP_HOST, MCP_PORT)
	$(RTFS) mcp --transport sse --host $(MCP_HOST) --port $(MCP_PORT)

cache-clear: ## Clear the local SQLite disk cache (~/.cache/rtfs)
	rm -rf $(CACHE_DIR)
	@echo "Cleared disk cache at $(CACHE_DIR)"

build: ## Build wheel and sdist packages into dist/
	$(UV) build

clean: ## Remove build artifacts, pytest/ruff caches, and bytecode
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache/ .ruff_cache/ .mypy_cache/ .coverage htmlcov/
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete

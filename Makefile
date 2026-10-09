PYTHON ?= python3
NPM ?= npm
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help setup build datasets dev test test-py test-web e2e lint typecheck validate audit check docker clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install Python and Node dependencies and the Playwright browser
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(NPM) install
	$(PYTHON) -m playwright install chromium

build: ## Build the web client into web/dist
	$(NPM) run build

datasets: ## Build the sample datasets into var/datasets
	$(PYTHON) -m joinery build-datasets

dev: build datasets ## Run the development server
	$(PYTHON) -m joinery serve --host $(HOST) --port $(PORT) --debug

test: test-py test-web ## Run Python and TypeScript unit tests

test-py: ## Run Python unit and integration tests
	$(PYTHON) -m unittest discover -s tests -t .

test-web: ## Run TypeScript unit tests with the Node test runner
	$(NPM) test

e2e: build ## Run browser end-to-end tests (needs Playwright and Chromium)
	JOINERY_E2E=1 $(PYTHON) -m unittest discover -s tests/e2e -t .

typecheck: ## Type-check the web client
	$(NPM) run typecheck

lint: typecheck ## Lint Python (ruff) and type-check TypeScript
	$(PYTHON) -m ruff check joinery tests scripts

validate: ## Run every lesson example and exercise against the SQLite engine
	$(PYTHON) -m joinery validate

audit: ## Check dependencies for known vulnerabilities
	$(PYTHON) -m pip_audit -r requirements-prod.txt
	$(NPM) audit

check: lint test validate build ## Everything CI runs except the browser tests

docker: ## Build the production container image
	docker build -t joinery:local .

clean: ## Remove build output and generated datasets
	rm -rf web/dist var test-results

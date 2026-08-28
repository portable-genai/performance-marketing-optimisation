# D4 Performance Marketing and Attribution — developer tasks.
#
# The gate (lint + format + types + tests + eval) runs on the local profile with the
# [dev] extra only (no google-cloud-*), matching CI. Override PROFILE=gcp for the managed
# stack, or PROFILE=onprem for the fail-fast migration target.

PY ?= python3.14
VENV ?= .venv
BIN := $(VENV)/bin
PROFILE ?= local

API_APP := performance_marketing.api.app:app
API_HOST ?= 127.0.0.1  # no-auth local dev binds loopback; override deliberately
API_PORT ?= 8103
UI_DIR := ui
DEMO_PORT ?= 8113
TF_DIR := infra/terraform
TF_REGION ?= asia-southeast1

export MKT_PERF_PROFILE := $(PROFILE)

.PHONY: venv install install-gcp lint format typecheck test eval gate \
        ui-install ui-check \
        demo demo-server demo-selftest smoke-local run-api run-ui tf-validate tf-plan clean

venv:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip

install: venv ## Install the package + dev tooling (NO GCP SDK — local/onprem profile).
	$(BIN)/python -m pip install -e ".[dev]"

install-gcp: ## Install with the managed-stack extra (google-genai, bigquery, ...).
	$(BIN)/python -m pip install -e ".[gcp,dev]"

lint:
	$(BIN)/ruff check src tests

format:
	$(BIN)/ruff format --check src tests

typecheck:
	$(BIN)/mypy src

test:
	$(BIN)/pytest -m "not integration" -q

eval:
	$(BIN)/python eval/run_eval.py

# The full gate, green before any change lands.
portability:
	PYTHONPATH=src $(BIN)/python scripts/portability_demo.py

plugin: ## Render the Agent Plugins 1.0.0 directory from this repo's own declarations.
	python scripts/render_plugin.py --dest dist/plugin

mcp-serve: ## Serve the governed tool catalog over MCP 2026-07-28 (stdio; needs [gcp]).
	python -m performance_marketing.mcp

gate: lint format typecheck test eval demo-selftest portability plugin

ui-install: ## Install the console's pinned dependencies exactly as CI does.
	npm ci --prefix $(UI_DIR)

ui-check: ## The console's gate: types, policy unit tests, build, then the HYDRATION proof.
	# `assert-hydratable` runs LAST and against the artefact the build just produced. It is the
	# only check here that executes the page: it starts the built server, fetches the served
	# document and asserts every script tag carries the served CSP nonce. A page whose scripts
	# are all blocked renders, type-checks, builds and screenshots exactly like a working one.
	npm --prefix $(UI_DIR) run lint
	npm --prefix $(UI_DIR) test
	NEXT_TELEMETRY_DISABLED=1 npm --prefix $(UI_DIR) run build
	npm --prefix $(UI_DIR) run assert-hydratable

demo: ## Offline demo: run the report flow + render the static audit-first HTML (scripts/out).
	MKT_PERF_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo.py
	MKT_PERF_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/render_report_ui.py scripts/out

demo-server: ## Live, presenter-controlled offline demo server on :$(DEMO_PORT).
	MKT_PERF_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_server.py --port $(DEMO_PORT)

demo-selftest:
	MKT_PERF_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_selftest.py

smoke-local: ## End-to-end offline smoke: build a cited report under the local profile.
	MKT_PERF_PROFILE=local $(BIN)/mkt-perf report acct-sg-banking -m SG -v banking

run-api: ## Run the real FastAPI service on :$(API_PORT) (PROFILE=$(PROFILE)).
	$(BIN)/uvicorn $(API_APP) --host $(API_HOST) --port $(API_PORT)

run-ui: ## Run the thin Next.js console (dev server); set NEXT_PUBLIC_API_BASE to the API.
	cd $(UI_DIR) && npm install && npm run dev

tf-plan: ## terraform plan for the pinned in-country region (checks the deploy posture).
	cd $(TF_DIR) && terraform init -input=false && terraform plan -var="region=$(TF_REGION)"

tf-validate:
	cd $(TF_DIR) && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

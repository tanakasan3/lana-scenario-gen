.PHONY: help dev install clean parse generate apply test-db

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CLI := $(VENV)/bin/lana-scenario

# Default lana-bank path (override with LANA_BANK_PATH=...)
LANA_BANK_PATH ?= $(HOME)/source/repos/lana-bank

help:
	@echo "lana-scenario-gen"
	@echo ""
	@echo "Usage:"
	@echo "  make dev                  Create venv and install"
	@echo "  make parse                Parse events from lana-bank"
	@echo "  make generate SCENARIO=x  Generate SQL from scenario"
	@echo "  make apply SCENARIO=x     Generate + execute scenario"
	@echo "  make test-db              Test database connection"
	@echo "  make clean                Remove venv and outputs"
	@echo ""
	@echo "Environment:"
	@echo "  LANA_BANK_PATH  Path to lana-bank (default: ~/source/repos/lana-bank)"
	@echo "  PG_CON          PostgreSQL connection string"
	@echo ""
	@echo "Examples:"
	@echo "  make dev"
	@echo "  make parse LANA_BANK_PATH=/path/to/lana-bank"
	@echo "  make generate SCENARIO=scenarios/happy_path_loan.yml"
	@echo "  make apply SCENARIO=scenarios/happy_path_loan.yml"

# Create venv and install
dev: $(VENV)/bin/activate
	@echo "✓ Dev environment ready. Activate with: source $(VENV)/bin/activate"

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]" 2>/dev/null || $(PIP) install -e .
	@touch $(VENV)/bin/activate

# Parse lana-bank events
parse: $(VENV)/bin/activate
	$(CLI) parse $(LANA_BANK_PATH)

# Generate SQL from scenario
generate: $(VENV)/bin/activate
ifndef SCENARIO
	@echo "Error: SCENARIO not set"
	@echo "Usage: make generate SCENARIO=scenarios/happy_path_loan.yml"
	@exit 1
endif
	$(CLI) generate $(SCENARIO)

# Apply scenario to database
apply: $(VENV)/bin/activate
ifndef SCENARIO
	@echo "Error: SCENARIO not set"
	@echo "Usage: make apply SCENARIO=scenarios/happy_path_loan.yml"
	@exit 1
endif
ifndef PG_CON
	@echo "Error: PG_CON not set"
	@echo "Usage: export PG_CON='postgresql://user:pass@localhost:5432/lana'"
	@exit 1
endif
	$(CLI) apply $(SCENARIO)

# Test database connection
test-db: $(VENV)/bin/activate
ifndef PG_CON
	@echo "Error: PG_CON not set"
	@exit 1
endif
	$(CLI) test-db

# List available events
list-events: $(VENV)/bin/activate
	$(CLI) list-events

# Clean up
clean:
	rm -rf $(VENV)
	rm -rf output/
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

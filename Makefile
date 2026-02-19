.PHONY: help dev install clean parse generate generate-all apply test-db list-events list-scenarios

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CLI := $(VENV)/bin/lana-scenario

# Default lana-bank path (override with LANA_BANK_PATH=...)
LANA_BANK_PATH ?= $(HOME)/source/repos/lana-bank

# Find all scenario files
SCENARIOS := $(shell find scenarios -name "*.yml" 2>/dev/null | sort)

help:
	@echo "lana-scenario-gen"
	@echo ""
	@echo "Usage:"
	@echo "  make dev                  Create venv and install"
	@echo "  make parse                Parse events from lana-bank"
	@echo "  make generate SCENARIO=x  Generate SQL from single scenario"
	@echo "  make generate-all         Generate SQL for ALL scenarios (42)"
	@echo "  make apply SCENARIO=x     Generate + execute scenario"
	@echo "  make test-db              Test database connection"
	@echo "  make list-events          List available events"
	@echo "  make list-scenarios       List all scenarios"
	@echo "  make clean                Remove venv and outputs"
	@echo ""
	@echo "Environment:"
	@echo "  LANA_BANK_PATH  Path to lana-bank (default: ~/source/repos/lana-bank)"
	@echo "  PG_CON          PostgreSQL connection string"
	@echo ""
	@echo "Examples:"
	@echo "  make dev"
	@echo "  make parse LANA_BANK_PATH=/path/to/lana-bank"
	@echo "  make generate SCENARIO=scenarios/loan/01_happy_path.yml"
	@echo "  make generate-all"

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

# Generate SQL from single scenario
generate: $(VENV)/bin/activate
ifndef SCENARIO
	@echo "Error: SCENARIO not set"
	@echo "Usage: make generate SCENARIO=scenarios/loan/01_happy_path.yml"
	@exit 1
endif
	$(CLI) generate $(SCENARIO)

# Generate SQL for ALL scenarios
generate-all: $(VENV)/bin/activate
	@echo "Generating SQL for all $(words $(SCENARIOS)) scenarios..."
	@mkdir -p output/loan output/payment output/collateral output/customer output/deposit output/edge
	@success=0; fail=0; \
	for scenario in $(SCENARIOS); do \
		name=$$(basename $$scenario .yml); \
		category=$$(dirname $$scenario | xargs basename); \
		outfile="output/$$category/$$name.sql"; \
		if $(CLI) generate $$scenario -o $$outfile 2>/dev/null; then \
			success=$$((success + 1)); \
		else \
			echo "  ✗ $$scenario"; \
			fail=$$((fail + 1)); \
		fi; \
	done; \
	echo ""; \
	echo "Generated: $$success succeeded, $$fail failed"; \
	echo "Output in: output/"

# Apply scenario to database
apply: $(VENV)/bin/activate
ifndef SCENARIO
	@echo "Error: SCENARIO not set"
	@echo "Usage: make apply SCENARIO=scenarios/loan/01_happy_path.yml"
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

# List all scenarios
list-scenarios:
	@echo "Available scenarios ($(words $(SCENARIOS)) total):"
	@echo ""
	@echo "Loan (12):"
	@find scenarios/loan -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'
	@echo ""
	@echo "Payment (6):"
	@find scenarios/payment -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'
	@echo ""
	@echo "Collateral (6):"
	@find scenarios/collateral -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'
	@echo ""
	@echo "Customer (5):"
	@find scenarios/customer -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'
	@echo ""
	@echo "Deposit (5):"
	@find scenarios/deposit -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'
	@echo ""
	@echo "Edge Cases (8):"
	@find scenarios/edge -name "*.yml" 2>/dev/null | sort | sed 's/^/  /'

# Clean up
clean:
	rm -rf $(VENV)
	rm -rf output/
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

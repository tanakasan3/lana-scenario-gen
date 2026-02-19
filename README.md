# Lana Scenario Generator

Generate SQL event data for lana-bank from scenario definitions. Parses Rust event enums and generates consistent INSERT statements for testing and simulation.

## Features

- **Auto-parse Rust events** — Scans lana-bank codebase for event enums
- **Scenario DSL** — Define timelines in YAML with external inputs
- **Smart field categorization** — Distinguishes flow-control vs identity fields
- **Consistent ID tracking** — Generates UUIDs that reference correctly
- **Direct DB execution** — Apply scenarios to PostgreSQL via `PG_CON`
- **Auto-generated docs** — Markdown documentation of all events

## Installation

```bash
git clone https://github.com/GaloyMoney/lana-scenario-gen.git
cd lana-scenario-gen

# Option 1: Makefile (creates venv)
make dev
source .venv/bin/activate

# Option 2: pip
pip install -e .
```

## Quick Start

### 1. Parse lana-bank events

```bash
# Point to your lana-bank clone
lana-scenario parse ~/source/repos/lana-bank

# Outputs:
#   output/schema.json       - Parsed event schema
#   output/EVENTS.md         - Documentation
#   output/scenario_template.yml - Template for scenarios
```

### 2. Generate SQL from a scenario

```bash
# Use a built-in scenario
lana-scenario generate scenarios/happy_path_loan.yml

# Or your own
lana-scenario generate my_scenario.yml -o output/my_scenario.sql
```

### 3. Apply to database

```bash
# Set connection string
export PG_CON='postgresql://user:pass@localhost:5432/lana'

# Test connection
lana-scenario test-db

# Apply scenario
lana-scenario apply scenarios/happy_path_loan.yml
```

## Scenario Format

```yaml
scenario:
  name: my_scenario
  description: What this tests

# External inputs (prices, amounts, etc.)
inputs:
  btc_price_usd: 50000
  loan_amount_usd: 10000
  collateral_btc: 0.5

# Customer definition
customer:
  email: test@example.com
  type: individual

# Timeline of events
timeline:
  - day: 0
    events:
      - type: CustomerEvent::Initialized
        params:
          customer_type: $customer.type
          level: Verified
      
      - type: DepositAccountEvent::Initialized

  - day: 1
    events:
      - type: DepositEvent::Initialized
        params:
          amount: $inputs.initial_deposit_usd
```

### Variable References

- `$inputs.field` — Reference input values
- `$customer.field` — Reference customer config
- `$entity_type.name` — Reference generated entity IDs

## Commands

```bash
lana-scenario parse <LANA_BANK_PATH>   # Parse event definitions
lana-scenario generate <SCENARIO>       # Generate SQL
lana-scenario run <SQL_FILE>            # Execute SQL file
lana-scenario apply <SCENARIO>          # Generate + execute
lana-scenario list-events               # List available events
lana-scenario test-db                   # Test DB connection
```

## Built-in Scenarios

| Scenario | Description |
|----------|-------------|
| `happy_path_loan.yml` | Full loan lifecycle: apply → approve → disburse → pay → complete |
| `loan_default.yml` | Missed payments → overdue → default → liquidation |

## Field Categories

The parser categorizes fields to help you understand what to provide:

| Category | Icon | Description | Example |
|----------|------|-------------|---------|
| `flow_control` | 🔵 | Affects logic (enums, statuses) | `status`, `approved` |
| `amount` | 💰 | Money/quantities | `amount`, `price` |
| `temporal` | ⏱️ | Dates/times | `due_date`, `recorded_at` |
| `config` | ⚙️ | Settings | `terms`, `rules` |
| `reference` | 🔗 | Foreign keys (auto-tracked) | `customer_id` |
| `identity` | 🆔 | Auto-generated IDs (skip) | `id`, `ledger_tx_id` |
| `metadata` | 📝 | Optional descriptive | `name`, `email` |

## Re-parsing After Code Changes

When lana-bank events change, just re-run parse:

```bash
lana-scenario parse ~/source/repos/lana-bank
```

The schema, docs, and templates will be regenerated.

## Requirements

- Python 3.10+
- PostgreSQL (for execution)
- lana-bank repository (for parsing)

## License

MIT

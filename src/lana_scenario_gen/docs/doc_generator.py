"""Generate markdown documentation from parsed event schema."""

from pathlib import Path
from datetime import datetime

from ..parser.schema import EventSchema, EventEnum, EventVariant, EventField, FieldCategory


# Deployment phases for organizing events
DEPLOYMENT_PHASES = {
    "Phase 1: System Bootstrap": [
        "PermissionSetEvent",
        "RoleEvent", 
        "UserEvent",
        "CommitteeEvent",
        "PolicyEvent",
        "ChartEvent",
        "ChartNodeEvent",
        "CustodianEvent",
        "WalletEvent",
        "DomainConfigEvent",
        "TermsTemplateEvent",
    ],
    "Phase 2: Customer Onboarding": [
        "PartyEvent",
        "CustomerEvent",
        "PublicIdEntityEvent",
        "DepositAccountEvent",
    ],
    "Phase 3: Deposit Operations": [
        "DepositEvent",
        "WithdrawalEvent",
    ],
    "Phase 4: Credit Facility Lifecycle": [
        "CreditFacilityProposalEvent",
        "ApprovalProcessEvent",
        "PendingCreditFacilityEvent",
        "CollateralEvent",
        "CreditFacilityEvent",
        "DisbursalEvent",
        "InterestAccrualCycleEvent",
        "ObligationEvent",
        "PaymentEvent",
        "PaymentAllocationEvent",
        "LiquidationEvent",
    ],
    "Phase 5: Reporting": [
        "ReportRunEvent",
        "ReportEvent",
    ],
}


def generate_docs(schema: EventSchema, output_path: str | Path) -> None:
    """Generate markdown documentation from event schema."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = [
        "# Lana Bank Event Schema Documentation",
        "",
        f"*Auto-generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*",
        "",
        f"*Source: `{schema.lana_bank_path}`*",
        "",
        "## Field Category Legend",
        "",
        "| Category | Description | Example |",
        "|----------|-------------|---------|",
        "| 🔵 **flow_control** | Affects scenario logic (enums, statuses) | `status`, `approved` |",
        "| 💰 **amount** | Monetary/quantity values (scenario input) | `amount`, `price` |",
        "| ⏱️ **temporal** | Dates and times (timeline driven) | `recorded_at`, `due_date` |",
        "| ⚙️ **config** | Configuration values (scenario input) | `terms`, `rules` |",
        "| 🔗 **reference** | Foreign keys (auto-tracked) | `customer_id` |",
        "| 🆔 ~~identity~~ | Auto-generated IDs (skip in scenarios) | `id`, `ledger_tx_id` |",
        "| 📝 ~~metadata~~ | Optional descriptive fields | `name`, `email` |",
        "",
        "---",
        "",
    ]
    
    # Organize events by deployment phase
    categorized = set()
    
    for phase_name, event_names in DEPLOYMENT_PHASES.items():
        phase_events = []
        for event_name in event_names:
            if event_name in schema.events:
                phase_events.append(schema.events[event_name])
                categorized.add(event_name)
        
        if phase_events:
            lines.append(f"## {phase_name}")
            lines.append("")
            for event in phase_events:
                lines.extend(format_event_enum(event))
    
    # Add uncategorized events
    uncategorized = [e for name, e in schema.events.items() if name not in categorized]
    if uncategorized:
        lines.append("## Other Events")
        lines.append("")
        for event in sorted(uncategorized, key=lambda e: e.name):
            lines.extend(format_event_enum(event))
    
    # Summary statistics
    lines.extend([
        "---",
        "",
        "## Summary Statistics",
        "",
        f"- **Total Event Types:** {len(schema.events)}",
        f"- **Total Variants:** {sum(len(e.variants) for e in schema.events.values())}",
        f"- **Total Fields:** {sum(len(v.fields) for e in schema.events.values() for v in e.variants)}",
        "",
    ])
    
    # Write to file
    output_path.write_text("\n".join(lines))


def format_event_enum(event: EventEnum) -> list[str]:
    """Format a single event enum as markdown."""
    lines = [
        f"### `{event.name}`",
        "",
        f"**Table:** `{event.table_name}`",
        "",
        f"**Source:** `{event.source_file}`",
        "",
    ]
    
    for variant in event.variants:
        lines.extend(format_variant(variant))
    
    lines.append("")
    return lines


def format_variant(variant: EventVariant) -> list[str]:
    """Format a single event variant as markdown."""
    lines = [
        f"#### `{variant.name}`",
        "",
    ]
    
    if not variant.fields:
        lines.append("*(No fields)*")
        lines.append("")
        return lines
    
    lines.append("| Field | Type | Category |")
    lines.append("|-------|------|----------|")
    
    for field in variant.fields:
        lines.append(format_field_row(field))
    
    lines.append("")
    return lines


def format_field_row(field: EventField) -> str:
    """Format a field as a markdown table row."""
    category = field.category
    
    # Format based on category
    if category == FieldCategory.IDENTITY:
        name_fmt = f"~~{field.name}~~"
        icon = "🆔"
    elif category == FieldCategory.METADATA:
        name_fmt = f"~~{field.name}~~"
        icon = "📝"
    elif category == FieldCategory.FLOW_CONTROL:
        name_fmt = f"**{field.name}**"
        icon = "🔵"
    elif category == FieldCategory.AMOUNT:
        name_fmt = f"**{field.name}**"
        icon = "💰"
    elif category == FieldCategory.TEMPORAL:
        name_fmt = f"**{field.name}**"
        icon = "⏱️"
    elif category == FieldCategory.CONFIG:
        name_fmt = f"**{field.name}**"
        icon = "⚙️"
    elif category == FieldCategory.REFERENCE:
        name_fmt = field.name
        icon = "🔗"
    else:
        name_fmt = field.name
        icon = ""
    
    type_str = field.rust_type
    if field.optional:
        type_str = f"Option<{type_str}>"
    
    return f"| {name_fmt} | `{type_str}` | {icon} {category.value} |"


def generate_scenario_template(schema: EventSchema, output_path: str | Path) -> None:
    """Generate a YAML scenario template with all available events."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = [
        "# Lana Bank Scenario Template",
        "# Auto-generated - customize for your scenario",
        "",
        "scenario:",
        "  name: example_scenario",
        "  description: |",
        "    Describe what this scenario tests",
        "",
        "# External inputs (prices, rates, etc.)",
        "inputs:",
        "  btc_price_usd: 50000",
        "  initial_deposit_usd: 100000",
        "  loan_amount_usd: 10000",
        "  collateral_btc: 0.5",
        "  annual_rate: 0.12",
        "",
        "# Customer definition",
        "customer:",
        "  email: test@example.com",
        "  telegram: test_user",
        "  type: individual  # individual | company",
        "",
        "# Timeline of events",
        "timeline:",
        "",
    ]
    
    # Add example timeline entries
    lines.extend([
        "  # Day 0: Customer onboarding",
        "  - day: 0",
        "    events:",
        "      - type: PartyEvent::Initialized",
        "        params:",
        "          email: $customer.email",
        "          telegram_handle: $customer.telegram",
        "          customer_type: $customer.type",
        "",
        "      - type: CustomerEvent::Initialized",
        "        params:",
        "          level: Verified",
        "",
        "      - type: DepositAccountEvent::Initialized",
        "",
        "  # Day 1: Make deposit",
        "  - day: 1",
        "    events:",
        "      - type: DepositEvent::Initialized",
        "        params:",
        "          amount: $inputs.initial_deposit_usd",
        "",
        "  # Day 2: Apply for loan",
        "  - day: 2",
        "    events:",
        "      - type: CreditFacilityProposalEvent::Initialized",
        "        params:",
        "          amount: $inputs.loan_amount_usd",
        "",
        "  # ... continue scenario",
        "",
        "# Available event types (from parsed schema):",
        "# " + "-" * 50,
    ])
    
    # List all available events
    for event_name, event in sorted(schema.events.items()):
        lines.append(f"# {event_name}:")
        for variant in event.variants:
            flow_fields = [f.name for f in variant.flow_control_fields]
            amount_fields = [f.name for f in variant.amount_fields]
            
            hint = ""
            if flow_fields:
                hint += f" flow={flow_fields}"
            if amount_fields:
                hint += f" amounts={amount_fields}"
            
            lines.append(f"#   - {variant.name}{hint}")
    
    output_path.write_text("\n".join(lines))

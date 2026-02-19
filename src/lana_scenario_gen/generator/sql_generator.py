"""Generate SQL INSERT statements from scenario definitions."""

import json
import yaml
from pathlib import Path
from typing import Any
from datetime import datetime

from ..parser.schema import EventSchema, EventEnum, FieldCategory
from .id_tracker import IdTracker, resolve_value


def generate_sql(
    schema: EventSchema,
    scenario_path: str | Path,
    output_path: str | Path,
) -> list[str]:
    """
    Generate SQL INSERT statements from a scenario definition.
    
    Args:
        schema: Parsed event schema
        scenario_path: Path to scenario YAML file
        output_path: Path to write SQL output
        
    Returns:
        List of SQL statements
    """
    scenario_path = Path(scenario_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load scenario
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)
    
    # Initialize tracker
    tracker = IdTracker()
    if "base_time" in scenario:
        tracker.base_time = datetime.fromisoformat(scenario["base_time"])
    
    # Get inputs
    inputs = scenario.get("inputs", {})
    
    # Pre-create customer IDs if defined
    if "customer" in scenario:
        customer_config = scenario["customer"]
        tracker.get_or_create("customer", "main")
        tracker.get_or_create("party", "main")
        tracker.get_or_create("deposit_account", "main")
    
    # Process timeline
    statements = []
    statements.append(f"-- Generated from: {scenario_path.name}")
    statements.append(f"-- Generated at: {datetime.utcnow().isoformat()}Z")
    statements.append(f"-- Scenario: {scenario.get('scenario', {}).get('name', 'unnamed')}")
    statements.append("")
    statements.append("BEGIN;")
    statements.append("")
    
    timeline = scenario.get("timeline", [])
    for entry in timeline:
        day = entry.get("day", 0)
        events = entry.get("events", [])
        
        if events:
            statements.append(f"-- Day {day}")
        
        for event_def in events:
            sql = generate_event_insert(
                event_def, schema, tracker, inputs, day, scenario
            )
            if sql:
                statements.extend(sql)
    
    statements.append("")
    statements.append("COMMIT;")
    
    # Write output
    sql_text = "\n".join(statements)
    output_path.write_text(sql_text)
    
    return statements


def generate_event_insert(
    event_def: dict,
    schema: EventSchema,
    tracker: IdTracker,
    inputs: dict,
    day: int,
    scenario: dict = None,
) -> list[str]:
    """Generate SQL INSERT for a single event."""
    event_type = event_def.get("type", "")
    params = event_def.get("params", {})
    
    # Parse event type (e.g., "CustomerEvent::Initialized")
    if "::" not in event_type:
        return [f"-- ERROR: Invalid event type format: {event_type}"]
    
    enum_name, variant_name = event_type.split("::")
    
    # Find event enum in schema
    if enum_name not in schema.events:
        return [f"-- WARNING: Unknown event type: {enum_name}"]
    
    event_enum = schema.events[enum_name]
    
    # Find variant
    variant = None
    for v in event_enum.variants:
        if v.name == variant_name:
            variant = v
            break
    
    if variant is None:
        return [f"-- WARNING: Unknown variant: {variant_name} in {enum_name}"]
    
    # Build event data
    event_data = {}
    event_data["type"] = variant_name.lower()
    
    # Generate/resolve field values
    for field in variant.fields:
        value = None
        
        # Check if provided in params
        if field.name in params:
            value = resolve_value(params[field.name], inputs, tracker, scenario)
        
        # Auto-generate based on category
        elif field.category == FieldCategory.IDENTITY:
            # Generate UUID for identity fields
            if field.name == "id":
                # Main entity ID - derive from event type
                entity_type = derive_entity_type(enum_name)
                value = tracker.get_or_create(entity_type)
            else:
                # Related entity ID
                related_type = field.name.replace("_id", "")
                # Check if we have this entity, otherwise generate
                value = tracker.get_or_create(related_type)
        
        elif field.category == FieldCategory.TEMPORAL:
            # Generate timestamp
            value = tracker.timestamp_str(day)
        
        elif field.category == FieldCategory.AMOUNT:
            # Default to 0 if not provided
            value = 0
        
        # Skip optional fields with no value
        if value is None and field.optional:
            continue
        
        if value is not None:
            event_data[field.name] = value
    
    # Get entity ID for this event
    entity_type = derive_entity_type(enum_name)
    entity_id = event_data.get("id") or tracker.get_or_create(entity_type)
    sequence = tracker.next_sequence(entity_id)
    
    # Build INSERT statement
    table_name = event_enum.table_name
    recorded_at = tracker.timestamp_str(day)
    
    event_json = json.dumps(event_data)
    
    sql = f"""INSERT INTO {table_name} (id, sequence, event_type, event, recorded_at)
VALUES ('{entity_id}', {sequence}, '{variant_name}', '{event_json}'::jsonb, '{recorded_at}');"""
    
    return [sql, ""]


def derive_entity_type(enum_name: str) -> str:
    """Derive entity type name from event enum name."""
    # CreditFacilityEvent -> credit_facility
    base = enum_name.replace("Event", "")
    # Convert to snake_case
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()


def load_scenario(scenario_path: str | Path) -> dict:
    """Load and validate a scenario file."""
    scenario_path = Path(scenario_path)
    
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)
    
    # Basic validation
    if "timeline" not in scenario:
        raise ValueError("Scenario must have a 'timeline' section")
    
    return scenario

"""Parse Rust event definitions from lana-bank codebase."""

import re
from pathlib import Path
from datetime import datetime
from typing import Iterator

from .schema import (
    EventSchema, EventEnum, EventVariant, EventField,
    FieldCategory, TYPE_CATEGORIES
)


def parse_lana_events(lana_bank_path: str | Path) -> EventSchema:
    """
    Parse all event enums from lana-bank Rust code.
    
    Args:
        lana_bank_path: Path to lana-bank repository root
        
    Returns:
        EventSchema containing all parsed events
    """
    lana_bank_path = Path(lana_bank_path)
    schema = EventSchema(
        parsed_at=datetime.utcnow().isoformat() + "Z",
        lana_bank_path=str(lana_bank_path),
    )
    
    # Find all entity.rs files in core/ that contain event enums
    for rs_file in find_event_files(lana_bank_path):
        for event_enum in parse_event_file(rs_file, lana_bank_path):
            schema.events[event_enum.name] = event_enum
    
    return schema


def find_event_files(lana_bank_path: Path) -> Iterator[Path]:
    """Find all Rust files containing event enum definitions."""
    # Look in core/ directory for entity.rs files
    core_path = lana_bank_path / "core"
    if core_path.exists():
        for rs_file in core_path.rglob("*.rs"):
            # Read file and check if it contains event enum
            content = rs_file.read_text()
            if re.search(r"pub enum \w+Event\s*\{", content):
                yield rs_file


def parse_event_file(rs_file: Path, lana_bank_path: Path) -> Iterator[EventEnum]:
    """Parse event enums from a Rust file."""
    content = rs_file.read_text()
    relative_path = rs_file.relative_to(lana_bank_path)
    
    # Find all event enum definitions
    # Pattern: pub enum SomethingEvent { ... }
    enum_pattern = re.compile(
        r"pub enum (\w+Event)\s*\{(.*?)\n\}",
        re.DOTALL
    )
    
    for match in enum_pattern.finditer(content):
        enum_name = match.group(1)
        enum_body = match.group(2)
        
        # Skip test/dummy events
        if "Dummy" in enum_name or "Test" in enum_name:
            continue
        
        # Derive table name from enum name
        table_name = derive_table_name(enum_name)
        
        variants = list(parse_variants(enum_body))
        
        yield EventEnum(
            name=enum_name,
            table_name=table_name,
            variants=variants,
            source_file=str(relative_path),
        )


def derive_table_name(enum_name: str) -> str:
    """
    Derive Postgres table name from event enum name.
    
    CreditFacilityEvent -> core_credit_facility_events
    InterestAccrualCycleEvent -> core_interest_accrual_cycle_events
    """
    # Remove 'Event' suffix
    base = enum_name.replace("Event", "")
    
    # Convert CamelCase to snake_case
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()
    
    return f"core_{snake}_events"


def parse_variants(enum_body: str) -> Iterator[EventVariant]:
    """Parse variants from an enum body."""
    # Pattern for variants with struct fields: VariantName { field: Type, ... }
    # or unit variants: VariantName,
    # or tuple variants: VariantName(Type),
    
    # Split by variant - look for PascalCase names followed by { or , or (
    variant_pattern = re.compile(
        r"(\w+)\s*(?:\{([^}]*)\}|(\([^)]*\))?)\s*,?",
        re.MULTILINE
    )
    
    for match in variant_pattern.finditer(enum_body):
        variant_name = match.group(1)
        fields_str = match.group(2)  # Struct fields
        
        # Skip if not a valid variant name (starts with uppercase)
        if not variant_name[0].isupper():
            continue
        
        # Skip common non-variant patterns
        if variant_name in ("Some", "None", "Ok", "Err"):
            continue
        
        fields = []
        if fields_str:
            fields = list(parse_fields(fields_str))
        
        yield EventVariant(
            name=variant_name,
            fields=fields,
        )


def parse_fields(fields_str: str) -> Iterator[EventField]:
    """Parse fields from a struct variant body."""
    # Pattern: field_name: Type
    # Handle optional (#[serde(default)]) and complex types
    
    # Clean up the string
    fields_str = re.sub(r"#\[.*?\]", "", fields_str)  # Remove attributes
    
    # Split by comma, handling nested generics
    parts = split_fields(fields_str)
    
    for part in parts:
        part = part.strip()
        if not part or ":" not in part:
            continue
        
        # Parse field_name: Type
        match = re.match(r"(\w+)\s*:\s*(.+)", part.strip())
        if not match:
            continue
        
        field_name = match.group(1)
        rust_type = match.group(2).strip()
        
        # Check if optional
        optional = rust_type.startswith("Option<")
        if optional:
            rust_type = rust_type[7:-1]  # Remove Option< and >
        
        # Categorize the field
        category = categorize_field(field_name, rust_type)
        
        yield EventField(
            name=field_name,
            rust_type=rust_type,
            category=category,
            optional=optional,
        )


def split_fields(fields_str: str) -> list[str]:
    """Split fields by comma, respecting nested generics."""
    parts = []
    current = []
    depth = 0
    
    for char in fields_str:
        if char in "<({":
            depth += 1
            current.append(char)
        elif char in ">)}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    
    if current:
        parts.append("".join(current))
    
    return parts


def categorize_field(field_name: str, rust_type: str) -> FieldCategory:
    """Categorize a field based on its name and type."""
    
    # Check type patterns
    for category, patterns in TYPE_CATEGORIES.items():
        for pattern in patterns:
            if re.match(pattern, rust_type):
                return category
    
    # Check field name patterns
    name_lower = field_name.lower()
    
    if name_lower.endswith("_id") or name_lower == "id":
        return FieldCategory.IDENTITY
    
    if any(x in name_lower for x in ["status", "state", "approved", "type"]):
        return FieldCategory.FLOW_CONTROL
    
    if any(x in name_lower for x in ["amount", "price", "rate", "ratio", "fee"]):
        return FieldCategory.AMOUNT
    
    if any(x in name_lower for x in ["date", "time", "at", "period"]):
        return FieldCategory.TEMPORAL
    
    if any(x in name_lower for x in ["name", "email", "description", "reference", "handle"]):
        return FieldCategory.METADATA
    
    # Default to metadata for unknown types
    return FieldCategory.METADATA

"""Parse Rust event definitions from lana-bank codebase."""

import re
from pathlib import Path
from datetime import datetime
from typing import Iterator

from .schema import (
    EventSchema, EventEnum, EventVariant, EventField,
    FieldCategory, TYPE_CATEGORIES, TypeDefinition, TypeRegistry,
    ScalarType, SerdeFormat
)


def parse_lana_events(lana_bank_path: str | Path) -> EventSchema:
    """
    Parse all event enums from lana-bank Rust code.
    
    Args:
        lana_bank_path: Path to lana-bank repository root
        
    Returns:
        EventSchema containing all parsed events with resolved types
    """
    lana_bank_path = Path(lana_bank_path)
    
    # First pass: build type registry from all Rust files
    type_registry = build_type_registry(lana_bank_path)
    
    schema = EventSchema(
        parsed_at=datetime.utcnow().isoformat() + "Z",
        lana_bank_path=str(lana_bank_path),
        type_registry=type_registry,
    )
    
    # Second pass: parse event enums and resolve their field types
    for rs_file in find_event_files(lana_bank_path):
        for event_enum in parse_event_file(rs_file, lana_bank_path, type_registry):
            schema.events[event_enum.name] = event_enum
    
    return schema


def build_type_registry(lana_bank_path: Path) -> TypeRegistry:
    """
    Build a registry of all type definitions from the codebase.
    Parses structs, newtypes, and enums.
    
    Priority: core/ types take precedence over lana/ types to ensure
    domain types aren't overwritten by GraphQL presentation types.
    """
    registry = TypeRegistry()
    core_types: set[str] = set()  # Track types from core/
    
    # Directories to scan - core first for priority
    scan_dirs = ["core", "lana"]
    
    for scan_dir in scan_dirs:
        dir_path = lana_bank_path / scan_dir
        if not dir_path.exists():
            continue
        
        for rs_file in dir_path.rglob("*.rs"):
            # Skip graphql directories - these are presentation types
            if "/graphql/" in str(rs_file) or "\\graphql\\" in str(rs_file):
                continue
            
            try:
                content = rs_file.read_text()
                relative_path = str(rs_file.relative_to(lana_bank_path))
                
                # Parse all type definitions
                for typedef in parse_type_definitions(content, relative_path):
                    # Don't overwrite core types with lana types
                    if scan_dir == "lana" and typedef.name in core_types:
                        continue
                    
                    registry.add(typedef)
                    
                    if scan_dir == "core":
                        core_types.add(typedef.name)
            except Exception:
                # Skip files we can't read
                continue
    
    return registry


def parse_type_definitions(content: str, source_file: str) -> Iterator[TypeDefinition]:
    """Parse all struct, newtype, and enum definitions from Rust content."""
    
    # Parse structs with named fields
    # pub struct Name { field: Type, ... }
    struct_pattern = re.compile(
        r"pub struct (\w+)\s*(?:<[^>]*>)?\s*\{([^}]+)\}",
        re.DOTALL
    )
    for match in struct_pattern.finditer(content):
        name = match.group(1)
        body = match.group(2)
        
        # Skip builder structs and internal types
        if name.endswith("Builder") or name.startswith("_"):
            continue
        
        fields = list(parse_struct_fields(body))
        if fields:
            yield TypeDefinition(
                name=name,
                kind="struct",
                source_file=source_file,
                fields=fields,
            )
    
    # Parse newtypes: pub struct Name(Type);
    newtype_pattern = re.compile(
        r"pub struct (\w+)\s*\(\s*(?:pub\s+)?([^)]+)\s*\)\s*;",
    )
    for match in newtype_pattern.finditer(content):
        name = match.group(1)
        inner = match.group(2).strip()
        
        # Skip if it looks like a tuple with multiple types
        if "," in inner:
            continue
        
        yield TypeDefinition(
            name=name,
            kind="newtype",
            source_file=source_file,
            inner_type=inner,
        )
    
    # Parse enums (non-event enums for type resolution)
    # Capture attributes before pub enum
    enum_pattern = re.compile(
        r"((?:#\[[^\]]*\]\s*)*)"  # Capture all attributes
        r"pub enum (\w+)\s*\{([^}]+)\}",
        re.DOTALL
    )
    for match in enum_pattern.finditer(content):
        attrs = match.group(1) or ""
        name = match.group(2)
        body = match.group(3)
        
        # Skip event enums (handled separately) and test enums
        if name.endswith("Event") or "Dummy" in name or "Test" in name:
            continue
        
        # Extract serde attributes
        serde_format, serde_rename = parse_serde_attrs(attrs)
        
        # parse_enum_variants now returns 3-tuples: (name, struct_fields, tuple_types)
        variants = list(parse_enum_variants(body))
        if variants:
            yield TypeDefinition(
                name=name,
                kind="enum",
                source_file=source_file,
                variants=variants,
                serde_format=serde_format,
                serde_rename=serde_rename,
            )


def parse_serde_attrs(attrs: str) -> tuple[SerdeFormat, str | None]:
    """
    Parse serde attributes to determine serialization format.
    
    Returns (serde_format, serde_rename)
    """
    serde_format = SerdeFormat.EXTERNAL
    serde_rename = None
    
    # Find #[serde(...)] attribute
    serde_match = re.search(r'#\[serde\(([^)]+)\)\]', attrs)
    if not serde_match:
        return serde_format, serde_rename
    
    serde_content = serde_match.group(1)
    
    # Check for tag and content
    has_tag = 'tag' in serde_content and 'tag' not in serde_content.replace('tag', '', 1).replace('"', '')  # crude check
    has_tag = re.search(r'\btag\s*=', serde_content) is not None
    has_content = re.search(r'\bcontent\s*=', serde_content) is not None
    has_untagged = 'untagged' in serde_content
    
    if has_untagged:
        serde_format = SerdeFormat.UNTAGGED
    elif has_tag and has_content:
        serde_format = SerdeFormat.ADJACENT
    elif has_tag:
        serde_format = SerdeFormat.INTERNAL
    
    # Extract rename_all
    rename_match = re.search(r'rename_all\s*=\s*"([^"]+)"', serde_content)
    if rename_match:
        serde_rename = rename_match.group(1)
    
    return serde_format, serde_rename


def parse_struct_fields(body: str) -> Iterator[tuple[str, str, bool]]:
    """Parse fields from a struct body. Yields (name, type, optional)."""
    # Clean up: remove attributes
    body = re.sub(r"#\[[^\]]*\]", "", body)
    
    # Split by comma, respecting nested generics
    parts = split_by_comma(body)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Remove pub if present
        part = re.sub(r"^\s*pub\s+", "", part)
        
        # Parse field_name: Type
        match = re.match(r"(\w+)\s*:\s*(.+)", part.strip())
        if not match:
            continue
        
        field_name = match.group(1)
        rust_type = match.group(2).strip()
        
        # Check if optional
        optional = rust_type.startswith("Option<")
        if optional:
            # Extract inner type
            rust_type = rust_type[7:-1].strip()
        
        yield (field_name, rust_type, optional)


def parse_enum_variants(body: str) -> Iterator[tuple[str, list[tuple[str, str]] | None, list[str] | None]]:
    """
    Parse enum variants.
    Yields (variant_name, struct_fields, tuple_types) where:
    - struct_fields is None for non-struct variants, or list of (field_name, field_type)
    - tuple_types is None for non-tuple variants, or list of types
    """
    # Clean up attributes
    body = re.sub(r"#\[[^\]]*\]", "", body)
    
    # Match variants
    # Unit variant: Name,
    # Struct variant: Name { field: Type, ... },
    # Tuple variant: Name(Type),
    
    lines = body.split("\n")
    current_variant = None
    brace_depth = 0
    field_buffer = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for variant start
        if brace_depth == 0:
            # Unit variant
            unit_match = re.match(r"^(\w+)\s*,?\s*$", line)
            if unit_match and unit_match.group(1)[0].isupper():
                yield (unit_match.group(1), None, None)
                continue
            
            # Start of struct variant
            struct_start = re.match(r"^(\w+)\s*\{(.*)$", line)
            if struct_start and struct_start.group(1)[0].isupper():
                current_variant = struct_start.group(1)
                rest = struct_start.group(2)
                brace_depth = 1
                
                # Check if it closes on same line
                if "}" in rest:
                    field_str = rest[:rest.index("}")]
                    fields = list(parse_variant_fields(field_str))
                    yield (current_variant, fields if fields else None, None)
                    current_variant = None
                    brace_depth = 0
                else:
                    field_buffer = [rest]
                continue
            
            # Tuple variant - capture inner types
            tuple_match = re.match(r"^(\w+)\s*\(([^)]+)\)\s*,?\s*$", line)
            if tuple_match and tuple_match.group(1)[0].isupper():
                inner_types_str = tuple_match.group(2)
                # Split by comma for multiple tuple fields
                inner_types = [t.strip() for t in split_by_comma(inner_types_str) if t.strip()]
                yield (tuple_match.group(1), None, inner_types)
                continue
        
        elif brace_depth > 0:
            # Inside a struct variant
            brace_depth += line.count("{") - line.count("}")
            
            if brace_depth <= 0:
                # End of variant
                if "}" in line:
                    field_buffer.append(line[:line.index("}")])
                
                field_str = " ".join(field_buffer)
                fields = list(parse_variant_fields(field_str))
                yield (current_variant, fields if fields else None, None)
                
                current_variant = None
                brace_depth = 0
                field_buffer = []
            else:
                field_buffer.append(line)


def parse_variant_fields(field_str: str) -> Iterator[tuple[str, str]]:
    """Parse fields from a variant body. Yields (name, type)."""
    parts = split_by_comma(field_str)
    
    for part in parts:
        part = part.strip()
        if not part or ":" not in part:
            continue
        
        match = re.match(r"(\w+)\s*:\s*(.+)", part.strip())
        if match:
            yield (match.group(1), match.group(2).strip())


def split_by_comma(s: str) -> list[str]:
    """Split by comma, respecting nested generics and braces."""
    parts = []
    current = []
    depth = 0
    
    for char in s:
        if char in "<({[":
            depth += 1
            current.append(char)
        elif char in ">)}]":
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


def find_event_files(lana_bank_path: Path) -> Iterator[Path]:
    """Find all Rust files containing event enum definitions."""
    core_path = lana_bank_path / "core"
    if core_path.exists():
        for rs_file in core_path.rglob("*.rs"):
            content = rs_file.read_text()
            if re.search(r"pub enum \w+Event\s*\{", content):
                yield rs_file


def parse_event_file(
    rs_file: Path, 
    lana_bank_path: Path,
    type_registry: TypeRegistry
) -> Iterator[EventEnum]:
    """Parse event enums from a Rust file."""
    content = rs_file.read_text()
    relative_path = rs_file.relative_to(lana_bank_path)
    
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
        
        table_name = derive_table_name(enum_name)
        variants = list(parse_event_variants(enum_body, type_registry))
        
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
    """
    base = enum_name.replace("Event", "")
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()
    return f"core_{snake}_events"


def parse_event_variants(
    enum_body: str, 
    type_registry: TypeRegistry
) -> Iterator[EventVariant]:
    """Parse variants from an event enum body."""
    # Clean attributes
    enum_body = re.sub(r"#\[[^\]]*\]", "", enum_body)
    
    # Pattern for struct variants
    variant_pattern = re.compile(
        r"(\w+)\s*\{([^}]*)\}",
        re.DOTALL
    )
    
    for match in variant_pattern.finditer(enum_body):
        variant_name = match.group(1)
        fields_str = match.group(2)
        
        if not variant_name[0].isupper():
            continue
        
        if variant_name in ("Some", "None", "Ok", "Err"):
            continue
        
        fields = list(parse_event_fields(fields_str, type_registry))
        
        yield EventVariant(
            name=variant_name,
            fields=fields,
        )
    
    # Also match unit variants (no fields)
    unit_pattern = re.compile(r"(\w+)\s*\{\s*\}")
    for match in unit_pattern.finditer(enum_body):
        variant_name = match.group(1)
        if variant_name[0].isupper() and variant_name not in ("Some", "None", "Ok", "Err"):
            yield EventVariant(name=variant_name, fields=[])


def parse_event_fields(
    fields_str: str, 
    type_registry: TypeRegistry
) -> Iterator[EventField]:
    """Parse fields from an event variant body with type resolution."""
    parts = split_by_comma(fields_str)
    
    for part in parts:
        part = part.strip()
        if not part or ":" not in part:
            continue
        
        match = re.match(r"(\w+)\s*:\s*(.+)", part.strip())
        if not match:
            continue
        
        field_name = match.group(1)
        rust_type = match.group(2).strip()
        
        # Check if optional
        optional = rust_type.startswith("Option<")
        type_for_resolution = rust_type
        if optional:
            type_for_resolution = rust_type[7:-1].strip()
        
        # Categorize the field
        category = categorize_field(field_name, type_for_resolution)
        
        # Resolve the type recursively
        resolved_type = type_registry.resolve(type_for_resolution)
        
        yield EventField(
            name=field_name,
            rust_type=rust_type,
            category=category,
            resolved_type=resolved_type,
            optional=optional,
        )


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

"""Track and generate consistent IDs across a scenario."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class IdTracker:
    """
    Track IDs and references across a scenario.
    
    Maintains mappings between logical names (e.g., "customer_1") and 
    generated UUIDs, ensuring consistency across events.
    """
    
    # Logical name -> UUID mapping
    ids: dict[str, str] = field(default_factory=dict)
    
    # Entity type -> sequence counter for auto-naming
    sequences: dict[str, int] = field(default_factory=dict)
    
    # Track event sequence numbers per entity
    event_sequences: dict[str, int] = field(default_factory=dict)
    
    # Base timestamp for the scenario
    base_time: datetime = field(default_factory=datetime.utcnow)
    
    def get_or_create(self, entity_type: str, name: str | None = None) -> str:
        """Get existing ID or create a new one."""
        if name is None:
            # Auto-generate name from sequence
            seq = self.sequences.get(entity_type, 0) + 1
            self.sequences[entity_type] = seq
            name = f"{entity_type}_{seq}"
        
        key = f"{entity_type}:{name}"
        
        if key not in self.ids:
            self.ids[key] = str(uuid.uuid4())
        
        return self.ids[key]
    
    def get(self, entity_type: str, name: str) -> str | None:
        """Get existing ID or None."""
        key = f"{entity_type}:{name}"
        return self.ids.get(key)
    
    def require(self, entity_type: str, name: str) -> str:
        """Get existing ID or raise error."""
        id_val = self.get(entity_type, name)
        if id_val is None:
            raise ValueError(f"Unknown {entity_type}: {name}")
        return id_val
    
    def next_sequence(self, entity_id: str) -> int:
        """Get next event sequence number for an entity."""
        seq = self.event_sequences.get(entity_id, 0)
        self.event_sequences[entity_id] = seq + 1
        return seq
    
    def timestamp_for_day(self, day: int, hour: int = 12, minute: int = 0) -> datetime:
        """Get timestamp for a specific day in the scenario."""
        return self.base_time + timedelta(days=day, hours=hour, minutes=minute)
    
    def date_for_day(self, day: int) -> str:
        """Get date string for a specific day."""
        dt = self.timestamp_for_day(day)
        return dt.strftime("%Y-%m-%d")
    
    def timestamp_str(self, day: int, hour: int = 12, minute: int = 0) -> str:
        """Get ISO timestamp string for a specific day."""
        dt = self.timestamp_for_day(day, hour, minute)
        return dt.isoformat() + "Z"


def resolve_value(value: Any, inputs: dict, tracker: IdTracker, scenario: dict = None) -> Any:
    """
    Resolve a value that may contain variable references.
    
    Supports:
    - $inputs.field_name -> look up in inputs dict
    - $customer.field_name -> look up in customer config
    - $entity_type.name -> look up ID from tracker (if registered)
    - Literal values
    """
    if not isinstance(value, str):
        return value
    
    if not value.startswith("$"):
        return value
    
    # Parse the reference
    parts = value[1:].split(".")
    
    if parts[0] == "inputs":
        # $inputs.field_name
        return inputs.get(parts[1])
    
    if parts[0] == "customer" and scenario:
        # $customer.field_name -> look up in customer config
        customer = scenario.get("customer", {})
        return customer.get(parts[1])
    
    if len(parts) == 2:
        # $entity_type.name -> try to get ID from tracker
        entity_type, name = parts
        existing = tracker.get(entity_type, name)
        if existing:
            return existing
        # If not found, return the raw value (might be a literal)
        return value
    
    return value

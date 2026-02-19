"""Track and generate consistent UUIDs for entities across events."""

import uuid
from typing import Any


class IdTracker:
    """
    Track entity IDs across a scenario to ensure consistency.
    
    Entities are referenced by logical names in scenarios (e.g., "customer_1"),
    and this tracker maintains the mapping to actual UUIDs.
    """
    
    def __init__(self, seed: int | None = None):
        """
        Initialize the ID tracker.
        
        Args:
            seed: Optional seed for deterministic UUID generation
        """
        self._ids: dict[str, str] = {}
        self._sequences: dict[str, int] = {}  # Track sequence numbers per entity
        self._seed = seed
        self._counter = 0
    
    def get_or_create(self, entity_type: str, logical_name: str) -> str:
        """
        Get or create a UUID for an entity.
        
        Args:
            entity_type: Type of entity (e.g., "customer", "credit_facility")
            logical_name: Logical name in scenario (e.g., "customer_1", "main_facility")
            
        Returns:
            UUID string
        """
        key = f"{entity_type}:{logical_name}"
        
        if key not in self._ids:
            if self._seed is not None:
                # Deterministic UUID based on seed and counter
                self._counter += 1
                self._ids[key] = str(uuid.UUID(int=self._seed + self._counter))
            else:
                self._ids[key] = str(uuid.uuid4())
        
        return self._ids[key]
    
    def get(self, entity_type: str, logical_name: str) -> str | None:
        """Get existing UUID or None if not found."""
        key = f"{entity_type}:{logical_name}"
        return self._ids.get(key)
    
    def require(self, entity_type: str, logical_name: str) -> str:
        """Get existing UUID or raise if not found."""
        uid = self.get(entity_type, logical_name)
        if uid is None:
            raise KeyError(f"Entity not found: {entity_type}:{logical_name}")
        return uid
    
    def next_sequence(self, entity_id: str) -> int:
        """
        Get next sequence number for an entity.
        Event tables use (id, sequence) as composite key.
        """
        if entity_id not in self._sequences:
            self._sequences[entity_id] = 0
        
        self._sequences[entity_id] += 1
        return self._sequences[entity_id]
    
    def new_uuid(self) -> str:
        """Generate a new random UUID (not tracked)."""
        if self._seed is not None:
            self._counter += 1
            return str(uuid.UUID(int=self._seed + self._counter))
        return str(uuid.uuid4())
    
    def all_ids(self) -> dict[str, str]:
        """Return all tracked IDs."""
        return dict(self._ids)
    
    def clear(self) -> None:
        """Clear all tracked IDs and sequences."""
        self._ids.clear()
        self._sequences.clear()
        self._counter = 0

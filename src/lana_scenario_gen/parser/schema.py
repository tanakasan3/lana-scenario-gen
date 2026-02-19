"""Event schema data models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json


class FieldCategory(str, Enum):
    """Categorize fields by their impact on scenario flow."""
    
    IDENTITY = "identity"           # UUIDs, IDs - auto-generated
    FLOW_CONTROL = "flow_control"   # Enums, statuses - affects logic
    AMOUNT = "amount"               # Money, quantities - scenario input
    TEMPORAL = "temporal"           # Dates, timestamps - timeline driven
    REFERENCE = "reference"         # Foreign keys - tracked internally
    CONFIG = "config"               # Settings, terms - scenario input
    METADATA = "metadata"           # Descriptions, names - optional input


# Type patterns to categorize fields
TYPE_CATEGORIES = {
    # Identity types (auto-generated)
    FieldCategory.IDENTITY: [
        r".*Id$", r"^Uuid$", r"^CalaAccountId$", r"^LedgerTxId$",
        r"^CalaTransactionId$", r"^CalaAccountSetId$",
    ],
    # Flow control (affects logic)
    FieldCategory.FLOW_CONTROL: [
        r".*Status$", r".*State$", r"^bool$", r"^approved$",
        r".*Type$", r".*Direction$", r".*Level$",
    ],
    # Amounts (scenario inputs)
    FieldCategory.AMOUNT: [
        r"^UsdCents$", r"^Satoshis$", r"^Decimal$", r".*Rate$",
        r".*Ratio$", r"^PriceOfOneBTC$", r".*Amount$",
    ],
    # Temporal (timeline driven)
    FieldCategory.TEMPORAL: [
        r"^DateTime<.*>$", r"^NaiveDate$", r"^chrono::.*$",
        r".*Date$", r".*At$", r".*Period$", r".*Interval$",
    ],
    # Config (scenario inputs)
    FieldCategory.CONFIG: [
        r"^TermValues$", r"^ApprovalRules$", r".*Config$",
        r".*Policy$", r".*Duration$",
    ],
}


@dataclass
class EventField:
    """A field within an event variant."""
    
    name: str
    rust_type: str
    category: FieldCategory
    optional: bool = False
    default: Any = None
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rust_type": self.rust_type,
            "category": self.category.value,
            "optional": self.optional,
            "default": self.default,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventField":
        return cls(
            name=data["name"],
            rust_type=data["rust_type"],
            category=FieldCategory(data["category"]),
            optional=data.get("optional", False),
            default=data.get("default"),
            description=data.get("description", ""),
        )


@dataclass
class EventVariant:
    """A variant of an event enum (e.g., Initialized, Updated)."""
    
    name: str
    fields: list[EventField] = field(default_factory=list)
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": [f.to_dict() for f in self.fields],
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventVariant":
        return cls(
            name=data["name"],
            fields=[EventField.from_dict(f) for f in data.get("fields", [])],
            description=data.get("description", ""),
        )
    
    @property
    def flow_control_fields(self) -> list[EventField]:
        return [f for f in self.fields if f.category == FieldCategory.FLOW_CONTROL]
    
    @property
    def amount_fields(self) -> list[EventField]:
        return [f for f in self.fields if f.category == FieldCategory.AMOUNT]
    
    @property
    def identity_fields(self) -> list[EventField]:
        return [f for f in self.fields if f.category == FieldCategory.IDENTITY]


@dataclass
class EventEnum:
    """An event enum (e.g., CreditFacilityEvent)."""
    
    name: str
    table_name: str
    variants: list[EventVariant] = field(default_factory=list)
    source_file: str = ""
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "table_name": self.table_name,
            "variants": [v.to_dict() for v in self.variants],
            "source_file": self.source_file,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventEnum":
        return cls(
            name=data["name"],
            table_name=data["table_name"],
            variants=[EventVariant.from_dict(v) for v in data.get("variants", [])],
            source_file=data.get("source_file", ""),
            description=data.get("description", ""),
        )


@dataclass
class EventSchema:
    """Complete schema of all events in lana-bank."""
    
    events: dict[str, EventEnum] = field(default_factory=dict)
    parsed_at: str = ""
    lana_bank_path: str = ""
    
    def to_dict(self) -> dict:
        return {
            "parsed_at": self.parsed_at,
            "lana_bank_path": self.lana_bank_path,
            "events": {k: v.to_dict() for k, v in self.events.items()},
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventSchema":
        return cls(
            parsed_at=data.get("parsed_at", ""),
            lana_bank_path=data.get("lana_bank_path", ""),
            events={k: EventEnum.from_dict(v) for k, v in data.get("events", {}).items()},
        )
    
    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> "EventSchema":
        with open(path) as f:
            return cls.from_dict(json.load(f))
    
    def get_table_for_event(self, event_name: str) -> str | None:
        """Get the Postgres table name for an event enum."""
        if event_name in self.events:
            return self.events[event_name].table_name
        return None

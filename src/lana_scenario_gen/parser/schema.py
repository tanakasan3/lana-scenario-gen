"""Event schema data models with recursive type resolution."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json


class SerdeFormat(str, Enum):
    """Serde serialization format for enums."""
    
    # Default: externally tagged - {"Variant": value} or "Variant" for unit
    EXTERNAL = "external"
    
    # #[serde(tag = "type")] - internally tagged, unit variants only
    # {"type": "variant_name"}
    INTERNAL = "internal"
    
    # #[serde(tag = "type", content = "value")] - adjacently tagged
    # {"type": "variant_name", "value": inner_value}
    ADJACENT = "adjacent"
    
    # #[serde(untagged)] - no tag, just the value
    UNTAGGED = "untagged"


class FieldCategory(str, Enum):
    """Categorize fields by their impact on scenario flow."""
    
    IDENTITY = "identity"           # UUIDs, IDs - auto-generated
    FLOW_CONTROL = "flow_control"   # Enums, statuses - affects logic
    AMOUNT = "amount"               # Money, quantities - scenario input
    TEMPORAL = "temporal"           # Dates, timestamps - timeline driven
    REFERENCE = "reference"         # Foreign keys - tracked internally
    CONFIG = "config"               # Settings, terms - scenario input
    METADATA = "metadata"           # Descriptions, names - optional input


class ScalarType(str, Enum):
    """Rust scalar types that don't need further resolution."""
    
    # Integers
    I8 = "i8"
    I16 = "i16"
    I32 = "i32"
    I64 = "i64"
    I128 = "i128"
    U8 = "u8"
    U16 = "u16"
    U32 = "u32"
    U64 = "u64"
    U128 = "u128"
    ISIZE = "isize"
    USIZE = "usize"
    
    # Floats
    F32 = "f32"
    F64 = "f64"
    
    # Other primitives
    BOOL = "bool"
    CHAR = "char"
    STRING = "String"
    STR = "str"
    
    # Common external types treated as scalars
    UUID = "Uuid"
    DECIMAL = "Decimal"
    DATETIME = "DateTime"
    NAIVE_DATE = "NaiveDate"
    
    @classmethod
    def is_scalar(cls, type_name: str) -> bool:
        """Check if a type name is a scalar."""
        # Strip generics
        base = type_name.split("<")[0].strip()
        try:
            cls(base)
            return True
        except ValueError:
            # Also check common scalar patterns
            return base in (
                "Uuid", "uuid::Uuid", 
                "Decimal", "rust_decimal::Decimal",
                "String", "str", "&str",
                "bool", "char",
                "i8", "i16", "i32", "i64", "i128",
                "u8", "u16", "u32", "u64", "u128",
                "f32", "f64",
                "isize", "usize",
            )


# Type patterns to categorize fields
TYPE_CATEGORIES = {
    # Identity types (auto-generated)
    FieldCategory.IDENTITY: [
        r".*Id$", r"^Uuid$", r"^CalaAccountId$", r"^LedgerTxId$",
        r"^CalaTransactionId$", r"^CalaAccountSetId$", r"^PublicId$",
    ],
    # Flow control (affects logic)
    FieldCategory.FLOW_CONTROL: [
        r".*Status$", r".*State$", r"^bool$", r"^approved$",
        r".*Type$", r".*Direction$", r".*Level$",
    ],
    # Amounts (scenario inputs)
    FieldCategory.AMOUNT: [
        r"^UsdCents$", r"^Satoshis$", r"^Decimal$", r".*Rate$",
        r".*Ratio$", r"^PriceOfOneBTC$", r".*Amount$", r".*Pct$",
    ],
    # Temporal (timeline driven)
    FieldCategory.TEMPORAL: [
        r"^DateTime<.*>$", r"^NaiveDate$", r"^chrono::.*$",
        r".*Date$", r".*At$", r".*Period$", r"^EffectiveDate$",
    ],
    # Config (scenario inputs)  
    FieldCategory.CONFIG: [
        r"^TermValues$", r"^ApprovalRules$", r".*Config$",
        r".*Policy$", r".*Duration$", r".*Interval$", r".*Cvl$",
    ],
}


@dataclass
class TypeField:
    """A field within a struct type."""
    
    name: str
    rust_type: str
    resolved_type: "ResolvedType | None" = None
    optional: bool = False
    description: str = ""
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "rust_type": self.rust_type,
            "optional": self.optional,
        }
        if self.resolved_type:
            result["resolved"] = self.resolved_type.to_dict()
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "TypeField":
        resolved = None
        if "resolved" in data:
            resolved = ResolvedType.from_dict(data["resolved"])
        return cls(
            name=data["name"],
            rust_type=data["rust_type"],
            resolved_type=resolved,
            optional=data.get("optional", False),
            description=data.get("description", ""),
        )


@dataclass
class ResolvedType:
    """
    A fully resolved type definition.
    
    Can be:
    - scalar: A primitive type (i32, String, bool, etc.)
    - struct: Has fields that are themselves resolved
    - newtype: Wraps a single inner type
    - enum: Has variants (each variant may have fields)
    - array/vec: Contains items of a resolved type
    - option: Wraps an optional resolved type
    """
    
    kind: str  # "scalar", "struct", "newtype", "enum", "vec", "option", "map"
    rust_type: str
    
    # For scalar
    scalar_type: str | None = None
    
    # For struct
    fields: list[TypeField] | None = None
    
    # For newtype (wraps single value)
    inner_type: "ResolvedType | None" = None
    
    # For enum
    variants: list["EnumVariant"] | None = None
    serde_format: SerdeFormat = SerdeFormat.EXTERNAL  # Serde tagging format
    serde_rename: str | None = None  # rename_all value (e.g., "snake_case")
    
    # For vec/option
    item_type: "ResolvedType | None" = None
    
    # For map
    key_type: "ResolvedType | None" = None
    value_type: "ResolvedType | None" = None
    
    def to_dict(self) -> dict:
        result = {
            "kind": self.kind,
            "rust_type": self.rust_type,
        }
        if self.scalar_type:
            result["scalar_type"] = self.scalar_type
        if self.fields:
            result["fields"] = [f.to_dict() for f in self.fields]
        if self.inner_type:
            result["inner_type"] = self.inner_type.to_dict()
        if self.variants:
            result["variants"] = [v.to_dict() for v in self.variants]
        if self.serde_format != SerdeFormat.EXTERNAL:
            result["serde_format"] = self.serde_format.value
        if self.serde_rename:
            result["serde_rename"] = self.serde_rename
        if self.item_type:
            result["item_type"] = self.item_type.to_dict()
        if self.key_type:
            result["key_type"] = self.key_type.to_dict()
        if self.value_type:
            result["value_type"] = self.value_type.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedType":
        fields = None
        if "fields" in data:
            fields = [TypeField.from_dict(f) for f in data["fields"]]
        
        variants = None
        if "variants" in data:
            variants = [EnumVariant.from_dict(v) for v in data["variants"]]
        
        inner_type = None
        if "inner_type" in data:
            inner_type = cls.from_dict(data["inner_type"])
        
        item_type = None
        if "item_type" in data:
            item_type = cls.from_dict(data["item_type"])
        
        key_type = None
        if "key_type" in data:
            key_type = cls.from_dict(data["key_type"])
            
        value_type = None
        if "value_type" in data:
            value_type = cls.from_dict(data["value_type"])
        
        serde_format = SerdeFormat.EXTERNAL
        if "serde_format" in data:
            serde_format = SerdeFormat(data["serde_format"])
        
        return cls(
            kind=data["kind"],
            rust_type=data["rust_type"],
            scalar_type=data.get("scalar_type"),
            fields=fields,
            inner_type=inner_type,
            variants=variants,
            serde_format=serde_format,
            serde_rename=data.get("serde_rename"),
            item_type=item_type,
            key_type=key_type,
            value_type=value_type,
        )
    
    @classmethod
    def scalar(cls, rust_type: str) -> "ResolvedType":
        """Create a scalar type."""
        return cls(kind="scalar", rust_type=rust_type, scalar_type=rust_type)
    
    @classmethod 
    def struct(cls, rust_type: str, fields: list[TypeField]) -> "ResolvedType":
        """Create a struct type."""
        return cls(kind="struct", rust_type=rust_type, fields=fields)
    
    @classmethod
    def newtype(cls, rust_type: str, inner: "ResolvedType") -> "ResolvedType":
        """Create a newtype wrapper."""
        return cls(kind="newtype", rust_type=rust_type, inner_type=inner)
    
    @classmethod
    def enum_type(
        cls, 
        rust_type: str, 
        variants: list["EnumVariant"],
        serde_format: SerdeFormat = SerdeFormat.EXTERNAL,
        serde_rename: str | None = None,
    ) -> "ResolvedType":
        """Create an enum type."""
        return cls(
            kind="enum", 
            rust_type=rust_type, 
            variants=variants,
            serde_format=serde_format,
            serde_rename=serde_rename,
        )
    
    @classmethod
    def vec(cls, rust_type: str, item: "ResolvedType") -> "ResolvedType":
        """Create a vec/array type."""
        return cls(kind="vec", rust_type=rust_type, item_type=item)
    
    @classmethod
    def option(cls, rust_type: str, inner: "ResolvedType") -> "ResolvedType":
        """Create an option type."""
        return cls(kind="option", rust_type=rust_type, inner_type=inner)
    
    def get_scenario_inputs(self, prefix: str = "") -> list[dict]:
        """
        Get all fields that can be scenario inputs (non-identity fields).
        Returns flat list with dotted paths.
        """
        inputs = []
        
        if self.kind == "scalar":
            return [{"path": prefix, "type": self.scalar_type}]
        
        elif self.kind == "struct" and self.fields:
            for f in self.fields:
                path = f"{prefix}.{f.name}" if prefix else f.name
                if f.resolved_type:
                    inputs.extend(f.resolved_type.get_scenario_inputs(path))
                else:
                    inputs.append({"path": path, "type": f.rust_type})
        
        elif self.kind == "newtype" and self.inner_type:
            inputs.extend(self.inner_type.get_scenario_inputs(prefix))
        
        elif self.kind == "enum" and self.variants:
            # For enums, the value itself is a scenario input
            inputs.append({
                "path": prefix, 
                "type": "enum",
                "variants": [v.name for v in self.variants]
            })
        
        return inputs


@dataclass
class EnumVariant:
    """A variant of an enum type."""
    
    name: str
    fields: list[TypeField] | None = None  # None for unit/tuple variants
    tuple_types: list[ResolvedType] | None = None  # For tuple variants like Months(u32)
    
    def to_dict(self) -> dict:
        result = {"name": self.name}
        if self.fields:
            result["fields"] = [f.to_dict() for f in self.fields]
        if self.tuple_types:
            result["tuple_types"] = [t.to_dict() for t in self.tuple_types]
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "EnumVariant":
        fields = None
        if "fields" in data:
            fields = [TypeField.from_dict(f) for f in data["fields"]]
        tuple_types = None
        if "tuple_types" in data:
            tuple_types = [ResolvedType.from_dict(t) for t in data["tuple_types"]]
        return cls(
            name=data["name"],
            fields=fields,
            tuple_types=tuple_types,
        )
    
    @property
    def is_unit(self) -> bool:
        return self.fields is None and self.tuple_types is None
    
    @property
    def is_struct(self) -> bool:
        return self.fields is not None
    
    @property
    def is_tuple(self) -> bool:
        return self.tuple_types is not None


@dataclass
class TypeDefinition:
    """
    A type definition parsed from Rust code.
    Used to build the type registry before resolution.
    """
    
    name: str
    kind: str  # "struct", "newtype", "enum"
    source_file: str = ""
    
    # For struct
    fields: list[tuple[str, str, bool]] | None = None  # (name, type, optional)
    
    # For newtype
    inner_type: str | None = None
    
    # For enum: list of (variant_name, struct_fields, tuple_types)
    # struct_fields: list of (field_name, field_type) or None
    # tuple_types: list of types for tuple variants or None
    variants: list[tuple[str, list[tuple[str, str]] | None, list[str] | None]] | None = None
    
    # Serde serialization info (for enums)
    serde_format: SerdeFormat = SerdeFormat.EXTERNAL
    serde_rename: str | None = None  # e.g., "snake_case"
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "kind": self.kind,
            "source_file": self.source_file,
            "fields": self.fields,
            "inner_type": self.inner_type,
            "variants": self.variants,
        }
        if self.serde_format != SerdeFormat.EXTERNAL:
            result["serde_format"] = self.serde_format.value
        if self.serde_rename:
            result["serde_rename"] = self.serde_rename
        return result


@dataclass
class EventField:
    """A field within an event variant."""
    
    name: str
    rust_type: str
    category: FieldCategory
    resolved_type: ResolvedType | None = None
    optional: bool = False
    default: Any = None
    description: str = ""
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "rust_type": self.rust_type,
            "category": self.category.value,
            "optional": self.optional,
        }
        if self.resolved_type:
            result["resolved"] = self.resolved_type.to_dict()
        if self.default is not None:
            result["default"] = self.default
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventField":
        resolved = None
        if "resolved" in data:
            resolved = ResolvedType.from_dict(data["resolved"])
        return cls(
            name=data["name"],
            rust_type=data["rust_type"],
            category=FieldCategory(data["category"]),
            resolved_type=resolved,
            optional=data.get("optional", False),
            default=data.get("default"),
            description=data.get("description", ""),
        )
    
    def is_scenario_input(self) -> bool:
        """Check if this field should be a scenario input."""
        return self.category in (
            FieldCategory.FLOW_CONTROL,
            FieldCategory.AMOUNT,
            FieldCategory.CONFIG,
            FieldCategory.TEMPORAL,
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
    
    @property
    def scenario_input_fields(self) -> list[EventField]:
        return [f for f in self.fields if f.is_scenario_input()]


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
class TypeRegistry:
    """Registry of all type definitions parsed from the codebase."""
    
    types: dict[str, TypeDefinition] = field(default_factory=dict)
    resolved_cache: dict[str, ResolvedType] = field(default_factory=dict)
    
    def add(self, typedef: TypeDefinition) -> None:
        self.types[typedef.name] = typedef
    
    def resolve(self, type_name: str, resolving: set[str] | None = None) -> ResolvedType:
        """
        Recursively resolve a type to its full structure.
        
        Args:
            type_name: The Rust type to resolve
            resolving: Set of types currently being resolved (cycle detection)
        """
        if resolving is None:
            resolving = set()
        
        # Check cache
        if type_name in self.resolved_cache:
            return self.resolved_cache[type_name]
        
        # Handle generics
        base_type, generic_args = self._parse_generic(type_name)
        
        # Handle Option<T>
        if base_type == "Option" and generic_args:
            inner = self.resolve(generic_args[0], resolving)
            result = ResolvedType.option(type_name, inner)
            self.resolved_cache[type_name] = result
            return result
        
        # Handle Vec<T>
        if base_type in ("Vec", "HashSet") and generic_args:
            item = self.resolve(generic_args[0], resolving)
            result = ResolvedType.vec(type_name, item)
            self.resolved_cache[type_name] = result
            return result
        
        # Handle HashMap<K, V>
        if base_type in ("HashMap", "BTreeMap") and len(generic_args) >= 2:
            key = self.resolve(generic_args[0], resolving)
            value = self.resolve(generic_args[1], resolving)
            result = ResolvedType(
                kind="map", rust_type=type_name,
                key_type=key, value_type=value
            )
            self.resolved_cache[type_name] = result
            return result
        
        # Check if scalar
        if ScalarType.is_scalar(base_type):
            result = ResolvedType.scalar(base_type)
            self.resolved_cache[type_name] = result
            return result
        
        # Cycle detection
        if base_type in resolving:
            # Return a reference placeholder for cycles
            return ResolvedType.scalar(f"<cycle:{base_type}>")
        
        # Look up in registry
        if base_type not in self.types:
            # Unknown type - treat as scalar
            result = ResolvedType.scalar(base_type)
            self.resolved_cache[type_name] = result
            return result
        
        typedef = self.types[base_type]
        resolving = resolving | {base_type}
        
        if typedef.kind == "struct" and typedef.fields:
            resolved_fields = []
            for fname, ftype, optional in typedef.fields:
                resolved = self.resolve(ftype, resolving)
                resolved_fields.append(TypeField(
                    name=fname,
                    rust_type=ftype,
                    resolved_type=resolved,
                    optional=optional,
                ))
            result = ResolvedType.struct(base_type, resolved_fields)
        
        elif typedef.kind == "newtype" and typedef.inner_type:
            inner = self.resolve(typedef.inner_type, resolving)
            result = ResolvedType.newtype(base_type, inner)
        
        elif typedef.kind == "enum" and typedef.variants:
            resolved_variants = []
            for variant_data in typedef.variants:
                # Handle both old (2-tuple) and new (3-tuple) format
                if len(variant_data) == 2:
                    vname, vfields = variant_data
                    vtuple_types = None
                else:
                    vname, vfields, vtuple_types = variant_data
                
                if vfields:
                    # Struct variant with named fields
                    resolved_fields = []
                    for fname, ftype in vfields:
                        resolved = self.resolve(ftype, resolving)
                        resolved_fields.append(TypeField(
                            name=fname,
                            rust_type=ftype,
                            resolved_type=resolved,
                        ))
                    resolved_variants.append(EnumVariant(
                        name=vname,
                        fields=resolved_fields,
                    ))
                elif vtuple_types:
                    # Tuple variant like Months(u32)
                    resolved_tuple = []
                    for ttype in vtuple_types:
                        resolved_tuple.append(self.resolve(ttype, resolving))
                    resolved_variants.append(EnumVariant(
                        name=vname,
                        tuple_types=resolved_tuple,
                    ))
                else:
                    # Unit variant
                    resolved_variants.append(EnumVariant(name=vname))
            result = ResolvedType.enum_type(
                base_type, 
                resolved_variants,
                serde_format=typedef.serde_format,
                serde_rename=typedef.serde_rename,
            )
        
        else:
            # Fallback to scalar
            result = ResolvedType.scalar(base_type)
        
        self.resolved_cache[type_name] = result
        return result
    
    def _parse_generic(self, type_name: str) -> tuple[str, list[str]]:
        """Parse a generic type into base type and arguments."""
        if "<" not in type_name:
            return type_name, []
        
        base = type_name[:type_name.index("<")]
        args_str = type_name[type_name.index("<")+1:type_name.rindex(">")]
        
        # Split args, respecting nested generics
        args = []
        current = []
        depth = 0
        for char in args_str:
            if char == "<":
                depth += 1
                current.append(char)
            elif char == ">":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            args.append("".join(current).strip())
        
        return base, args
    
    def to_dict(self) -> dict:
        return {
            "types": {k: v.to_dict() for k, v in self.types.items()},
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TypeRegistry":
        registry = cls()
        for name, typedef_data in data.get("types", {}).items():
            registry.types[name] = TypeDefinition(
                name=typedef_data["name"],
                kind=typedef_data["kind"],
                source_file=typedef_data.get("source_file", ""),
                fields=typedef_data.get("fields"),
                inner_type=typedef_data.get("inner_type"),
                variants=typedef_data.get("variants"),
            )
        return registry


@dataclass
class EventSchema:
    """Complete schema of all events in lana-bank."""
    
    events: dict[str, EventEnum] = field(default_factory=dict)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    parsed_at: str = ""
    lana_bank_path: str = ""
    
    def to_dict(self) -> dict:
        return {
            "parsed_at": self.parsed_at,
            "lana_bank_path": self.lana_bank_path,
            "events": {k: v.to_dict() for k, v in self.events.items()},
            "types": self.type_registry.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EventSchema":
        registry = TypeRegistry.from_dict(data.get("types", {}))
        return cls(
            parsed_at=data.get("parsed_at", ""),
            lana_bank_path=data.get("lana_bank_path", ""),
            events={k: EventEnum.from_dict(v) for k, v in data.get("events", {}).items()},
            type_registry=registry,
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

"""Schema analysis utilities for dry-run and validation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Type, get_args, get_origin, Any, Union
from pydantic import BaseModel


@dataclass
class EnumInfo:
    """Information about an enum in a schema."""
    name: str
    value_count: int
    values: list[str]


@dataclass
class SchemaAnalysis:
    """Analysis of a Pydantic schema structure."""
    name: str
    total_fields: int
    required_fields: int
    optional_fields: int
    nested_models: list[str]
    enums: list[EnumInfo]
    estimated_output_tokens: int = 0

    @property
    def total_enum_values(self) -> int:
        """Total count of all enum values across all enums."""
        return sum(e.value_count for e in self.enums)

    def format_summary(self) -> str:
        """Format analysis as human-readable summary.

        Note: estimated_output_tokens is not shown here because it's per-document.
        The caller should display it with proper context (e.g., multiplied by doc count).
        """
        lines = [
            f"  Fields: {self.total_fields} ({self.required_fields} required, {self.optional_fields} optional)",
        ]

        if self.nested_models:
            lines.append(f"  Nested models: {len(self.nested_models)} ({', '.join(self.nested_models)})")

        if self.enums:
            enum_details = ", ".join(f"{e.name}: {e.value_count}" for e in self.enums)
            lines.append(f"  Enums: {len(self.enums)} ({enum_details})")
            lines.append(f"  Total enum values: {self.total_enum_values}")

        return "\n".join(lines)


# Token estimation constants (conservative estimates)
TOKENS_PER_FIELD_KEY = 3      # {"field_name": ...}
TOKENS_PER_STRING = 20        # Average string value
TOKENS_PER_STRING_LONG = 50   # Description/notes fields
TOKENS_PER_NUMBER = 3         # Numbers are compact
TOKENS_PER_BOOL = 1           # true/false
TOKENS_PER_ENUM = 3           # Enum value string
TOKENS_PER_DATE = 4           # "2024-01-15"
TOKENS_PER_LIST_ITEM = 5      # Overhead per list item
TOKENS_LIST_BASE = 2          # [] brackets
DEFAULT_LIST_ITEMS = 3        # Assume 3 items in lists


def estimate_output_tokens(schema: Type[BaseModel], seen: set[Type] = None) -> int:
    """Estimate output tokens for a schema based on field types.

    This is a rough estimate useful for cost planning.
    Actual tokens vary based on content.
    """
    if seen is None:
        seen = set()

    if schema in seen:
        return 0  # Avoid infinite recursion
    seen.add(schema)

    total = 2  # {} braces

    for field_name, field_info in schema.model_fields.items():
        # Key tokens
        total += TOKENS_PER_FIELD_KEY

        # Value tokens based on type
        total += _estimate_field_tokens(field_info.annotation, field_name, seen)

    return total


def _estimate_field_tokens(type_hint: Any, field_name: str, seen: set[Type]) -> int:
    """Estimate tokens for a single field value."""
    if type_hint is None:
        return TOKENS_PER_STRING

    origin = get_origin(type_hint)

    # Handle Optional[X] - estimate for the inner type
    if origin is Union:
        args = [a for a in get_args(type_hint) if a is not type(None)]
        if args:
            return _estimate_field_tokens(args[0], field_name, seen)
        return TOKENS_PER_STRING

    # Handle list[X]
    if origin in (list, set, frozenset):
        args = get_args(type_hint)
        if args:
            item_tokens = _estimate_field_tokens(args[0], field_name, seen)
            return TOKENS_LIST_BASE + (DEFAULT_LIST_ITEMS * (item_tokens + TOKENS_PER_LIST_ITEM))
        return TOKENS_LIST_BASE + (DEFAULT_LIST_ITEMS * TOKENS_PER_STRING)

    # Handle dict
    if origin is dict:
        return 20  # Rough estimate for dict

    # Check for specific types
    if type_hint is str:
        # Longer estimates for typical description/notes fields
        if any(kw in field_name.lower() for kw in ['description', 'notes', 'summary', 'comment', 'address']):
            return TOKENS_PER_STRING_LONG
        return TOKENS_PER_STRING

    if type_hint in (int, float):
        return TOKENS_PER_NUMBER

    if type_hint is bool:
        return TOKENS_PER_BOOL

    # Check for date types
    type_name = getattr(type_hint, '__name__', str(type_hint))
    if 'date' in type_name.lower() or 'time' in type_name.lower():
        return TOKENS_PER_DATE

    # Enum
    if isinstance(type_hint, type) and issubclass(type_hint, Enum):
        return TOKENS_PER_ENUM

    # Nested Pydantic model
    if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):
        return estimate_output_tokens(type_hint, seen)

    # Default
    return TOKENS_PER_STRING


def analyze_schema(schema: Type[BaseModel], name: str = None) -> SchemaAnalysis:
    """Analyze a Pydantic schema for fields, nested models, and enums.

    Recursively traverses nested models to find all enums.

    Args:
        schema: Pydantic BaseModel class to analyze
        name: Optional name override (defaults to class name)

    Returns:
        SchemaAnalysis with field counts, nested models, and enum info
    """
    if name is None:
        name = schema.__name__

    # Track what we've seen to avoid infinite recursion
    seen_models: set[Type] = set()
    nested_models: list[str] = []
    enums: list[EnumInfo] = []

    # Count fields
    model_fields = schema.model_fields
    total_fields = len(model_fields)
    required_fields = sum(1 for f in model_fields.values() if f.is_required())
    optional_fields = total_fields - required_fields

    # Estimate output tokens
    estimated_tokens = estimate_output_tokens(schema)

    def process_type(type_hint: Any) -> None:
        """Recursively process a type hint to find nested models and enums."""
        if type_hint is None:
            return

        # Handle Optional, Union, list, etc.
        origin = get_origin(type_hint)
        if origin is Union:
            # Optional[X] is Union[X, None]
            for arg in get_args(type_hint):
                if arg is not type(None):
                    process_type(arg)
            return

        if origin in (list, set, frozenset, tuple):
            for arg in get_args(type_hint):
                process_type(arg)
            return

        if origin is dict:
            args = get_args(type_hint)
            if len(args) >= 2:
                process_type(args[1])  # Process value type
            return

        # Check if it's an enum
        if isinstance(type_hint, type) and issubclass(type_hint, Enum):
            if type_hint not in seen_models:
                seen_models.add(type_hint)
                enum_values = [e.value for e in type_hint]
                enums.append(EnumInfo(
                    name=type_hint.__name__,
                    value_count=len(enum_values),
                    values=enum_values,
                ))
            return

        # Check if it's a nested Pydantic model
        if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):
            if type_hint not in seen_models and type_hint != schema:
                seen_models.add(type_hint)
                nested_models.append(type_hint.__name__)
                # Recurse into nested model's fields
                for nested_field in type_hint.model_fields.values():
                    process_type(nested_field.annotation)
            return

    # Process all fields in the schema
    for field_info in model_fields.values():
        process_type(field_info.annotation)

    return SchemaAnalysis(
        name=name,
        total_fields=total_fields,
        required_fields=required_fields,
        optional_fields=optional_fields,
        nested_models=nested_models,
        enums=enums,
        estimated_output_tokens=estimated_tokens,
    )

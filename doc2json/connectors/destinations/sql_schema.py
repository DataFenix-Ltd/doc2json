"""Shared schema definitions for SQL-based destinations.

This module defines the canonical schema for extractions and metadata tables,
plus helper functions for transforming records. Database-specific connectors
can use these definitions to ensure consistency.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ColumnType(Enum):
    """Logical column types that map to database-specific types."""

    # Auto-incrementing primary key
    SERIAL = "serial"

    # Basic types
    INTEGER = "integer"
    TEXT = "text"
    BOOLEAN = "boolean"

    # JSON storage (maps to JSONB, VARIANT, JSON depending on DB)
    JSON = "json"

    # Timestamps
    TIMESTAMP = "timestamp"


@dataclass
class Column:
    """Column definition with logical type."""

    name: str
    type: ColumnType
    nullable: bool = True
    default: str | None = None  # SQL expression for default
    primary_key: bool = False


# Canonical schema for extractions table
EXTRACTIONS_COLUMNS = [
    Column("id", ColumnType.SERIAL, nullable=False, primary_key=True),
    Column("source_file", ColumnType.TEXT, nullable=False),
    Column("schema_name", ColumnType.TEXT, nullable=False),
    Column("schema_version", ColumnType.TEXT),
    Column("extracted_at", ColumnType.TIMESTAMP, default="CURRENT_TIMESTAMP"),
    Column("data", ColumnType.JSON, nullable=False),
    Column("error", ColumnType.TEXT),
    Column("truncated", ColumnType.BOOLEAN, default="FALSE"),
]

# Canonical schema for metadata table
METADATA_COLUMNS = [
    Column("id", ColumnType.SERIAL, nullable=False, primary_key=True),
    Column("extraction_id", ColumnType.INTEGER),  # FK to extractions.id
    Column("source_file", ColumnType.TEXT, nullable=False),
    Column("started_at", ColumnType.TIMESTAMP),
    Column("completed_at", ColumnType.TIMESTAMP),
    Column("duration_ms", ColumnType.INTEGER),
    Column("success", ColumnType.BOOLEAN, default="TRUE"),
    Column("provider", ColumnType.TEXT),
    Column("model", ColumnType.TEXT),
    Column("char_count", ColumnType.INTEGER),
    Column("page_count", ColumnType.INTEGER),
    Column("truncated", ColumnType.BOOLEAN, default="FALSE"),
    Column("input_tokens", ColumnType.INTEGER),
    Column("output_tokens", ColumnType.INTEGER),
    Column("error", ColumnType.TEXT),
]

# Indexes to create
EXTRACTIONS_INDEXES = ["schema_name", "source_file", "extracted_at"]
METADATA_INDEXES = ["extraction_id", "source_file"]


def transform_record(record: dict[str, Any]) -> dict[str, Any]:
    """Transform an extraction record into database row format.

    Separates underscore-prefixed metadata fields from the actual data payload.

    Args:
        record: Raw record from engine with _source_file, _schema, etc.

    Returns:
        Dict with column names matching EXTRACTIONS_COLUMNS
    """
    # Extract the actual data (everything except underscore-prefixed fields)
    data = {k: v for k, v in record.items() if not k.startswith("_")}

    return {
        "source_file": record.get("_source_file", ""),
        "schema_name": record.get("_schema", ""),
        "schema_version": record.get("_schema_version"),
        "data": data,
        "error": record.get("_error"),
        "truncated": record.get("_truncated", False),
    }


def transform_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Transform metadata dict into database row format.

    Args:
        metadata: Raw metadata from engine

    Returns:
        Dict with column names matching METADATA_COLUMNS, or None if not an extraction record
    """
    # Skip run summary - we only want per-extraction metadata
    if metadata.get("_type") != "extraction":
        return None

    # Extract token counts from nested structure
    extract_tokens = metadata.get("extract_tokens", {})
    assess_tokens = metadata.get("assess_tokens", {})
    input_tokens = extract_tokens.get("input", 0) + assess_tokens.get("input", 0)
    output_tokens = extract_tokens.get("output", 0) + assess_tokens.get("output", 0)

    return {
        "source_file": metadata.get("source_file", ""),
        "started_at": metadata.get("started_at"),
        "completed_at": metadata.get("completed_at"),
        "duration_ms": metadata.get("duration_ms"),
        "success": metadata.get("success", True),
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "char_count": metadata.get("char_count"),
        "page_count": metadata.get("page_count"),
        "truncated": metadata.get("truncated", False),
        "input_tokens": input_tokens if input_tokens else None,
        "output_tokens": output_tokens if output_tokens else None,
        "error": metadata.get("error"),
    }

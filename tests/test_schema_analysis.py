"""Tests for schema analysis utilities."""

import pytest
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from doc2json.core.schema_analysis import analyze_schema, SchemaAnalysis, EnumInfo


class TestAnalyzeSchema:
    """Tests for analyze_schema function."""

    def test_simple_schema(self):
        """Test analysis of simple schema with no nesting."""
        class Simple(BaseModel):
            name: str
            value: int
            optional_field: Optional[str] = None

        analysis = analyze_schema(Simple)

        assert analysis.name == "Simple"
        assert analysis.total_fields == 3
        assert analysis.required_fields == 2
        assert analysis.optional_fields == 1
        assert analysis.nested_models == []
        assert analysis.enums == []

    def test_schema_with_enum(self):
        """Test analysis of schema with enum field."""
        class Status(str, Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"
            PENDING = "pending"

        class WithEnum(BaseModel):
            name: str
            status: Status

        analysis = analyze_schema(WithEnum)

        assert analysis.total_fields == 2
        assert len(analysis.enums) == 1
        assert analysis.enums[0].name == "Status"
        assert analysis.enums[0].value_count == 3
        assert analysis.total_enum_values == 3

    def test_schema_with_nested_model(self):
        """Test analysis of schema with nested Pydantic model."""
        class Address(BaseModel):
            street: str
            city: str

        class Person(BaseModel):
            name: str
            address: Address

        analysis = analyze_schema(Person)

        assert analysis.total_fields == 2
        assert "Address" in analysis.nested_models

    def test_schema_with_nested_enum(self):
        """Test that enums in nested models are found."""
        class Priority(str, Enum):
            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"

        class Task(BaseModel):
            title: str
            priority: Priority

        class Project(BaseModel):
            name: str
            tasks: list[Task]

        analysis = analyze_schema(Project)

        assert "Task" in analysis.nested_models
        assert len(analysis.enums) == 1
        assert analysis.enums[0].name == "Priority"
        assert analysis.enums[0].value_count == 3

    def test_schema_with_multiple_enums(self):
        """Test analysis with multiple enums."""
        class Status(str, Enum):
            OPEN = "open"
            CLOSED = "closed"

        class Priority(str, Enum):
            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"

        class Ticket(BaseModel):
            title: str
            status: Status
            priority: Priority

        analysis = analyze_schema(Ticket)

        assert len(analysis.enums) == 2
        assert analysis.total_enum_values == 5  # 2 + 3

    def test_schema_with_list_of_models(self):
        """Test analysis of schema with list of nested models."""
        class LineItem(BaseModel):
            description: str
            amount: float

        class Invoice(BaseModel):
            number: str
            items: list[LineItem]

        analysis = analyze_schema(Invoice)

        assert "LineItem" in analysis.nested_models

    def test_schema_with_optional_nested(self):
        """Test analysis with Optional nested model."""
        class Details(BaseModel):
            notes: str

        class Item(BaseModel):
            name: str
            details: Optional[Details] = None

        analysis = analyze_schema(Item)

        assert "Details" in analysis.nested_models

    def test_deeply_nested_enums(self):
        """Test that deeply nested enums are found."""
        class Color(str, Enum):
            RED = "red"
            BLUE = "blue"

        class Style(BaseModel):
            color: Color

        class Widget(BaseModel):
            style: Style

        class Dashboard(BaseModel):
            widgets: list[Widget]

        analysis = analyze_schema(Dashboard)

        assert "Widget" in analysis.nested_models
        assert "Style" in analysis.nested_models
        assert len(analysis.enums) == 1
        assert analysis.enums[0].name == "Color"

    def test_no_duplicate_enums(self):
        """Test that same enum used multiple times is counted once."""
        class Status(str, Enum):
            A = "a"
            B = "b"

        class Item(BaseModel):
            status1: Status
            status2: Status

        analysis = analyze_schema(Item)

        assert len(analysis.enums) == 1  # Not 2

    def test_custom_name(self):
        """Test providing custom name."""
        class MySchema(BaseModel):
            field: str

        analysis = analyze_schema(MySchema, name="custom_name")

        assert analysis.name == "custom_name"


class TestSchemaAnalysisFormatting:
    """Tests for SchemaAnalysis formatting."""

    def test_format_summary_simple(self):
        """Test formatting simple analysis."""
        analysis = SchemaAnalysis(
            name="Test",
            total_fields=5,
            required_fields=3,
            optional_fields=2,
            nested_models=[],
            enums=[],
        )
        summary = analysis.format_summary()

        assert "Fields: 5" in summary
        assert "3 required" in summary
        assert "2 optional" in summary

    def test_format_summary_with_nested(self):
        """Test formatting with nested models."""
        analysis = SchemaAnalysis(
            name="Test",
            total_fields=5,
            required_fields=5,
            optional_fields=0,
            nested_models=["Address", "Contact"],
            enums=[],
        )
        summary = analysis.format_summary()

        assert "Nested models: 2" in summary
        assert "Address" in summary
        assert "Contact" in summary

    def test_format_summary_with_enums(self):
        """Test formatting with enums."""
        analysis = SchemaAnalysis(
            name="Test",
            total_fields=3,
            required_fields=3,
            optional_fields=0,
            nested_models=[],
            enums=[
                EnumInfo(name="Status", value_count=3, values=["a", "b", "c"]),
                EnumInfo(name="Priority", value_count=2, values=["low", "high"]),
            ],
        )
        summary = analysis.format_summary()

        assert "Enums: 2" in summary
        assert "Status: 3" in summary
        assert "Priority: 2" in summary
        assert "Total enum values: 5" in summary

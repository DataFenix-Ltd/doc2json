"""Tests for schema loading functionality."""

import pytest
from pathlib import Path
from pydantic import BaseModel

from doc2json.core.extraction import load_schema, load_schema_module, get_schema_version
from doc2json.core.exceptions import SchemaNotFoundError, SchemaValidationError


class TestLoadSchemaModule:
    """Tests for load_schema_module function."""

    def test_load_valid_module(self, temp_dir, sample_schema_code):
        """Test loading a valid schema module."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "invoice.py"
        schema_file.write_text(sample_schema_code)

        module = load_schema_module("invoice", str(schemas_dir))

        assert hasattr(module, "Schema")
        assert hasattr(module, "__version__")

    def test_missing_schema_file(self, temp_dir):
        """Test error when schema file doesn't exist."""
        with pytest.raises(SchemaNotFoundError) as exc_info:
            load_schema_module("nonexistent", str(temp_dir))

        assert "Schema file not found" in str(exc_info.value)


class TestLoadSchema:
    """Tests for load_schema function."""

    def test_load_valid_schema(self, temp_dir, sample_schema_code):
        """Test loading a valid Pydantic schema."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "test.py"
        schema_file.write_text(sample_schema_code)

        schema_class = load_schema("test", str(schemas_dir))

        assert issubclass(schema_class, BaseModel)
        assert "title" in schema_class.model_fields

    def test_schema_without_schema_class(self, temp_dir):
        """Test error when module doesn't define Schema class."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "bad.py"
        schema_file.write_text("""
from pydantic import BaseModel

class Invoice(BaseModel):
    title: str
""")

        with pytest.raises(SchemaValidationError) as exc_info:
            load_schema("bad", str(schemas_dir))

        assert "must define a 'Schema' class" in str(exc_info.value)

    def test_schema_not_basemodel(self, temp_dir):
        """Test error when Schema is not a Pydantic BaseModel."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "not_pydantic.py"
        schema_file.write_text("""
class Schema:
    title: str
""")

        with pytest.raises(SchemaValidationError) as exc_info:
            load_schema("not_pydantic", str(schemas_dir))

        assert "must inherit from pydantic.BaseModel" in str(exc_info.value)

    def test_schema_with_syntax_error(self, temp_dir):
        """Test error handling for schema with syntax error."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "syntax_error.py"
        schema_file.write_text("""
from pydantic import BaseModel

class Schema(BaseModel)
    title: str  # missing colon above
""")

        with pytest.raises(SyntaxError):
            load_schema("syntax_error", str(schemas_dir))

    def test_schema_with_import_error(self, temp_dir):
        """Test error handling for schema with missing import."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "import_error.py"
        schema_file.write_text("""
from nonexistent_package import Something

class Schema(Something):
    title: str
""")

        with pytest.raises(ModuleNotFoundError):
            load_schema("import_error", str(schemas_dir))


class TestGetSchemaVersion:
    """Tests for get_schema_version function."""

    def test_get_version(self, temp_dir, sample_schema_code):
        """Test getting version from schema file."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "versioned.py"
        schema_file.write_text(sample_schema_code)

        version = get_schema_version("versioned", str(schemas_dir))
        assert version == "1"

    def test_version_not_defined(self, temp_dir):
        """Test default version when __version__ not defined."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "no_version.py"
        schema_file.write_text("""
from pydantic import BaseModel

class Schema(BaseModel):
    title: str
""")

        version = get_schema_version("no_version", str(schemas_dir))
        assert version == "unknown"

    def test_numeric_version(self, temp_dir):
        """Test schema with numeric version string."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "v2.py"
        schema_file.write_text('''__version__ = "2"

from pydantic import BaseModel

class Schema(BaseModel):
    title: str
''')

        version = get_schema_version("v2", str(schemas_dir))
        assert version == "2"


class TestSchemaFieldValidation:
    """Tests for schema field definitions and validation."""

    def test_schema_fields_have_descriptions(self, temp_dir, sample_schema_code):
        """Test that schema fields include descriptions."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "described.py"
        schema_file.write_text(sample_schema_code)

        schema_class = load_schema("described", str(schemas_dir))
        schema_json = schema_class.model_json_schema()

        # Check that fields have descriptions
        properties = schema_json.get("properties", {})
        assert "title" in properties
        assert "description" in properties["title"]

    def test_optional_fields(self, temp_dir, sample_schema_code):
        """Test that optional fields are properly defined."""
        schemas_dir = temp_dir / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "optional.py"
        schema_file.write_text(sample_schema_code)

        schema_class = load_schema("optional", str(schemas_dir))

        # Create instance with only required fields
        instance = schema_class(title="Test")
        assert instance.title == "Test"
        assert instance.amount is None
        assert instance.date is None

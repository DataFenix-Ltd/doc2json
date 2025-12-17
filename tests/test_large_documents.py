"""Tests for large document handling."""

import pytest
from unittest.mock import Mock, patch

from doc2json.models.document import (
    DocumentInfo,
    LARGE_DOC_CHARS,
    LARGE_DOC_PAGES,
    MAX_CHARS_DEFAULT,
)
from doc2json.config.loader import SchemaConfig, LargeDocStrategy, load_config
from doc2json.core.exceptions import DocumentTooLargeError
from doc2json.core.engine import SchemaTool
from doc2json.models.result import ExtractionResult


class TestDocumentInfo:
    """Tests for DocumentInfo dataclass."""

    def test_basic_creation(self):
        """Test creating DocumentInfo."""
        info = DocumentInfo(
            file_path="/test/doc.pdf",
            char_count=1000,
            page_count=5,
        )
        assert info.file_path == "/test/doc.pdf"
        assert info.char_count == 1000
        assert info.page_count == 5

    def test_estimated_tokens(self):
        """Test token estimation (chars / 4)."""
        info = DocumentInfo(file_path="/test.txt", char_count=4000)
        assert info.estimated_tokens == 1000

    def test_is_large_by_chars(self):
        """Test large detection by character count."""
        small = DocumentInfo(file_path="/test.txt", char_count=LARGE_DOC_CHARS - 1)
        assert small.is_large is False

        large = DocumentInfo(file_path="/test.txt", char_count=LARGE_DOC_CHARS + 1)
        assert large.is_large is True

    def test_is_large_by_pages(self):
        """Test large detection by page count."""
        small = DocumentInfo(
            file_path="/test.pdf",
            char_count=1000,
            page_count=LARGE_DOC_PAGES - 1,
        )
        assert small.is_large is False

        large = DocumentInfo(
            file_path="/test.pdf",
            char_count=1000,
            page_count=LARGE_DOC_PAGES + 1,
        )
        assert large.is_large is True

    def test_exceeds_limit(self):
        """Test exceeds_limit method."""
        info = DocumentInfo(file_path="/test.txt", char_count=50000)
        assert info.exceeds_limit(100000) is False
        assert info.exceeds_limit(40000) is True

    def test_str_representation(self):
        """Test string representation."""
        info = DocumentInfo(
            file_path="/test.pdf",
            char_count=10000,
            page_count=5,
        )
        s = str(info)
        assert "10,000 chars" in s
        assert "5 pages" in s
        assert "2,500 tokens" in s


class TestSchemaConfigLargeDoc:
    """Tests for large_doc_strategy in SchemaConfig."""

    def test_default_strategy(self):
        """Test default strategy is truncate."""
        config = SchemaConfig(name="test")
        assert config.large_doc_strategy == LargeDocStrategy.TRUNCATE
        assert config.max_chars == MAX_CHARS_DEFAULT

    def test_custom_strategy(self):
        """Test setting custom strategy."""
        config = SchemaConfig(
            name="test",
            large_doc_strategy=LargeDocStrategy.FAIL,
            max_chars=50000,
        )
        assert config.large_doc_strategy == LargeDocStrategy.FAIL
        assert config.max_chars == 50000

    def test_load_config_with_strategy(self, tmp_path):
        """Test loading config with large_doc_strategy."""
        config_file = tmp_path / "doc2json.yml"
        config_file.write_text("""
schemas:
  - name: invoices
    large_doc_strategy: fail
    max_chars: 50000
  - name: contracts
    large_doc_strategy: full

llm:
  provider: anthropic
""")
        config = load_config(str(config_file))

        invoices = config.get_schema("invoices")
        assert invoices.large_doc_strategy == LargeDocStrategy.FAIL
        assert invoices.max_chars == 50000

        contracts = config.get_schema("contracts")
        assert contracts.large_doc_strategy == LargeDocStrategy.FULL

    def test_load_config_invalid_strategy(self, tmp_path):
        """Test error on invalid strategy."""
        config_file = tmp_path / "doc2json.yml"
        config_file.write_text("""
schemas:
  - name: test
    large_doc_strategy: invalid_strategy

llm:
  provider: anthropic
""")
        from doc2json.core.exceptions import ConfigError
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        assert "invalid_strategy" in str(exc_info.value)


class TestSizeStrategyApplication:
    """Tests for applying size strategies in SchemaTool."""

    def create_mock_config(self, strategy: LargeDocStrategy, max_chars: int = 1000):
        """Create a mock config with specified strategy."""
        schema_config = SchemaConfig(
            name="test",
            large_doc_strategy=strategy,
            max_chars=max_chars,
        )
        config = Mock()
        config.schemas = [schema_config]
        config.get_schema = Mock(return_value=schema_config)
        config.llm = Mock(provider="anthropic", model="test-model")
        return config, schema_config

    def test_small_doc_unchanged(self):
        """Test small documents pass through unchanged."""
        config, schema_config = self.create_mock_config(
            LargeDocStrategy.TRUNCATE, max_chars=1000
        )
        tool = SchemaTool(config)

        text = "Short document"
        doc_info = DocumentInfo(file_path="/test.txt", char_count=len(text))

        result_text, was_truncated = tool._apply_size_strategy(
            text, doc_info, schema_config
        )

        assert result_text == text
        assert was_truncated is False

    def test_truncate_strategy(self):
        """Test truncate strategy cuts text and adds marker."""
        config, schema_config = self.create_mock_config(
            LargeDocStrategy.TRUNCATE, max_chars=100
        )
        tool = SchemaTool(config)

        text = "A" * 500  # 500 chars, limit is 100
        doc_info = DocumentInfo(file_path="/test.txt", char_count=len(text))

        result_text, was_truncated = tool._apply_size_strategy(
            text, doc_info, schema_config
        )

        assert len(result_text) < len(text)
        assert result_text.startswith("A" * 100)
        assert "truncated" in result_text.lower()
        assert was_truncated is True

    def test_fail_strategy_raises(self):
        """Test fail strategy raises DocumentTooLargeError."""
        config, schema_config = self.create_mock_config(
            LargeDocStrategy.FAIL, max_chars=100
        )
        tool = SchemaTool(config)

        text = "A" * 500
        doc_info = DocumentInfo(file_path="/test.txt", char_count=len(text))

        with pytest.raises(DocumentTooLargeError) as exc_info:
            tool._apply_size_strategy(text, doc_info, schema_config)

        assert exc_info.value.char_count == 500
        assert exc_info.value.max_chars == 100

    def test_full_strategy_passes_through(self):
        """Test full strategy passes document unchanged with warning."""
        config, schema_config = self.create_mock_config(
            LargeDocStrategy.FULL, max_chars=100
        )
        tool = SchemaTool(config)

        text = "A" * 500
        doc_info = DocumentInfo(file_path="/test.txt", char_count=len(text))

        result_text, was_truncated = tool._apply_size_strategy(
            text, doc_info, schema_config
        )

        assert result_text == text
        assert was_truncated is False


class TestExtractionResultTruncation:
    """Tests for truncation metadata in ExtractionResult."""

    def test_result_without_truncation(self):
        """Test output dict without truncation."""
        result = ExtractionResult(
            source_file="test.pdf",
            schema_name="invoice",
            schema_version="1",
            data={"field": "value"},
        )
        output = result.to_output_dict()

        assert "_truncated" not in output
        assert "_original_chars" not in output

    def test_result_with_truncation(self):
        """Test output dict includes truncation info."""
        result = ExtractionResult(
            source_file="test.pdf",
            schema_name="invoice",
            schema_version="1",
            data={"field": "value"},
            truncated=True,
            original_chars=150000,
        )
        output = result.to_output_dict()

        assert output["_truncated"] is True
        assert output["_original_chars"] == 150000


class TestDocumentTooLargeError:
    """Tests for DocumentTooLargeError exception."""

    def test_error_attributes(self):
        """Test error has correct attributes."""
        error = DocumentTooLargeError(
            message="Document too large",
            char_count=200000,
            max_chars=100000,
        )
        assert error.char_count == 200000
        assert error.max_chars == 100000
        assert "Document too large" in str(error)

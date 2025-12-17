"""Tests for document parsers."""

import pytest
from pathlib import Path

from doc2json.core.parsers import ParserRegistry, parse_document, register_parser
from doc2json.core.parsers.text import TextParser
from doc2json.core.exceptions import UnsupportedFileTypeError


class TestTextParser:
    """Tests for TextParser."""

    def test_can_parse_txt(self):
        """Test that .txt files are recognized."""
        parser = TextParser()
        assert parser.can_parse("document.txt") is True
        assert parser.can_parse("path/to/file.txt") is True

    def test_can_parse_md(self):
        """Test that markdown files are recognized."""
        parser = TextParser()
        assert parser.can_parse("README.md") is True
        assert parser.can_parse("docs/guide.markdown") is True

    def test_cannot_parse_other_types(self):
        """Test that non-text files are rejected."""
        parser = TextParser()
        assert parser.can_parse("document.pdf") is False
        assert parser.can_parse("image.png") is False
        assert parser.can_parse("data.json") is False

    def test_case_insensitive_extension(self):
        """Test that extension matching is case-insensitive."""
        parser = TextParser()
        assert parser.can_parse("FILE.TXT") is True
        assert parser.can_parse("README.MD") is True

    def test_parse_file(self, temp_dir):
        """Test parsing a text file."""
        text_file = temp_dir / "test.txt"
        text_file.write_text("Hello, World!\nLine 2")

        parser = TextParser()
        content = parser.parse(str(text_file))

        assert content == "Hello, World!\nLine 2"

    def test_parse_utf8(self, temp_dir):
        """Test parsing UTF-8 content."""
        text_file = temp_dir / "unicode.txt"
        text_file.write_text("Cafe with accents: \u00e9\u00e8\u00ea")

        parser = TextParser()
        content = parser.parse(str(text_file))

        assert "\u00e9" in content

    def test_parse_missing_file(self):
        """Test error when file doesn't exist."""
        parser = TextParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.txt")


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def test_register_and_get_parser(self):
        """Test registering and retrieving a parser."""
        registry = ParserRegistry()
        parser = TextParser()
        registry.register(parser)

        retrieved = registry.get_parser("test.txt")
        assert retrieved is parser

    def test_no_parser_available(self):
        """Test error when no parser can handle file."""
        registry = ParserRegistry()
        # Empty registry
        with pytest.raises(UnsupportedFileTypeError) as exc_info:
            registry.get_parser("document.pdf")

        assert ".pdf" in str(exc_info.value)

    def test_parser_selection_order(self):
        """Test that first matching parser is returned."""
        registry = ParserRegistry()

        class CustomTextParser:
            def can_parse(self, path):
                return path.endswith(".txt")

            def parse(self, path):
                return "custom"

        custom = CustomTextParser()
        registry.register(custom)
        registry.register(TextParser())

        # First registered parser should be used
        retrieved = registry.get_parser("test.txt")
        assert retrieved is custom

    def test_parse_through_registry(self, temp_dir):
        """Test parsing through registry convenience method."""
        registry = ParserRegistry()
        registry.register(TextParser())

        text_file = temp_dir / "test.txt"
        text_file.write_text("Content here")

        content = registry.parse(str(text_file))
        assert content == "Content here"


class TestGlobalRegistry:
    """Tests for global parser registry functions."""

    def test_parse_document_txt(self, temp_dir):
        """Test global parse_document function with text file."""
        text_file = temp_dir / "sample.txt"
        text_file.write_text("Sample content")

        content = parse_document(str(text_file))
        assert content == "Sample content"

    def test_parse_document_unsupported(self, temp_dir):
        """Test global parse_document with unsupported file type."""
        xlsx_file = temp_dir / "spreadsheet.xlsx"
        xlsx_file.write_text("fake xlsx")

        with pytest.raises(UnsupportedFileTypeError) as exc_info:
            parse_document(str(xlsx_file))

        assert ".xlsx" in str(exc_info.value)

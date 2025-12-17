"""Tests for DOCX parser."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Skip all tests if DOCX dependency isn't installed
pytest.importorskip("docx")

from doc2json.core.parsers.docx import DOCXParser
from doc2json.core.exceptions import ParserError


class TestDOCXParserBasics:
    """Basic tests for DOCXParser."""

    def test_can_parse_docx(self):
        """Test that DOCX files are recognized."""
        parser = DOCXParser()
        assert parser.can_parse("document.docx") is True
        assert parser.can_parse("path/to/file.DOCX") is True
        assert parser.can_parse("/absolute/path/doc.docx") is True

    def test_cannot_parse_other_types(self):
        """Test that non-DOCX files are rejected."""
        parser = DOCXParser()
        assert parser.can_parse("document.doc") is False  # Old Word format
        assert parser.can_parse("document.txt") is False
        assert parser.can_parse("document.pdf") is False
        assert parser.can_parse("document.odt") is False

    def test_default_settings(self):
        """Test default parser settings."""
        parser = DOCXParser()
        assert parser.include_tables is True

    def test_custom_settings(self):
        """Test custom parser settings."""
        parser = DOCXParser(include_tables=False)
        assert parser.include_tables is False


class TestDOCXParserWithMocks:
    """Tests using mocked python-docx."""

    def _create_mock_paragraph(self, text: str):
        """Create a mock paragraph object."""
        para = Mock()
        para.text = text
        return para

    def _create_mock_cell(self, text: str):
        """Create a mock table cell."""
        cell = Mock()
        cell.text = text
        return cell

    def _create_mock_row(self, cells: list[str]):
        """Create a mock table row."""
        row = Mock()
        row.cells = [self._create_mock_cell(text) for text in cells]
        return row

    def _create_mock_table(self, rows: list[list[str]]):
        """Create a mock table."""
        table = Mock()
        table.rows = [self._create_mock_row(cells) for cells in rows]
        return table

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_parse_paragraphs(self, mock_exists, mock_document):
        """Test parsing document with paragraphs."""
        parser = DOCXParser()

        # Create mock document
        mock_doc = Mock()
        mock_doc.paragraphs = [
            self._create_mock_paragraph("First paragraph"),
            self._create_mock_paragraph(""),  # Empty paragraph
            self._create_mock_paragraph("Second paragraph"),
        ]
        mock_doc.tables = []
        mock_document.return_value = mock_doc

        result = parser.parse("/fake/doc.docx")

        assert "First paragraph" in result
        assert "Second paragraph" in result
        # Empty paragraphs should be skipped
        assert result.count("\n\n") == 1  # One separator between two paragraphs

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_parse_with_tables(self, mock_exists, mock_document):
        """Test parsing document with tables."""
        parser = DOCXParser(include_tables=True)

        mock_doc = Mock()
        mock_doc.paragraphs = [
            self._create_mock_paragraph("Document title"),
        ]
        mock_doc.tables = [
            self._create_mock_table([
                ["Name", "Value"],
                ["Item 1", "100"],
                ["Item 2", "200"],
            ])
        ]
        mock_document.return_value = mock_doc

        result = parser.parse("/fake/doc.docx")

        assert "Document title" in result
        assert "Name | Value" in result
        assert "Item 1 | 100" in result

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_parse_without_tables(self, mock_exists, mock_document):
        """Test parsing with tables disabled."""
        parser = DOCXParser(include_tables=False)

        mock_doc = Mock()
        mock_doc.paragraphs = [
            self._create_mock_paragraph("Text content"),
        ]
        mock_doc.tables = [
            self._create_mock_table([["Should", "Not", "Appear"]])
        ]
        mock_document.return_value = mock_doc

        result = parser.parse("/fake/doc.docx")

        assert "Text content" in result
        assert "Should" not in result

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_parse_empty_document(self, mock_exists, mock_document):
        """Test parsing empty document."""
        parser = DOCXParser()

        mock_doc = Mock()
        mock_doc.paragraphs = []
        mock_doc.tables = []
        mock_document.return_value = mock_doc

        result = parser.parse("/fake/doc.docx")

        assert result == ""


class TestDOCXParserMetadata:
    """Tests for metadata extraction."""

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_get_metadata(self, mock_exists, mock_document):
        """Test extracting document metadata."""
        parser = DOCXParser()

        # Create mock properties
        mock_props = Mock()
        mock_props.title = "Test Document"
        mock_props.author = "John Doe"
        mock_props.subject = "Testing"
        mock_props.keywords = "test, docx"
        mock_props.created = None
        mock_props.modified = None
        mock_props.last_modified_by = "Jane Doe"

        mock_doc = Mock()
        mock_doc.core_properties = mock_props
        mock_document.return_value = mock_doc

        metadata = parser.get_metadata("/fake/doc.docx")

        assert metadata["title"] == "Test Document"
        assert metadata["author"] == "John Doe"
        assert metadata["subject"] == "Testing"
        assert metadata["last_modified_by"] == "Jane Doe"


class TestDOCXParserAnalyze:
    """Tests for document analysis."""

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_analyze_document(self, mock_exists, mock_document):
        """Test analyzing document structure."""
        parser = DOCXParser()

        # Create mock paragraphs
        mock_para1 = Mock()
        mock_para1.text = "First paragraph with some content"

        mock_para2 = Mock()
        mock_para2.text = ""  # Empty

        mock_para3 = Mock()
        mock_para3.text = "Third paragraph"

        # Create mock table
        mock_cell = Mock()
        mock_cell.text = "Cell content"
        mock_row = Mock()
        mock_row.cells = [mock_cell]
        mock_table = Mock()
        mock_table.rows = [mock_row]

        mock_doc = Mock()
        mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
        mock_doc.tables = [mock_table]
        mock_document.return_value = mock_doc

        analysis = parser.analyze("/fake/doc.docx")

        assert analysis["paragraph_count"] == 2  # Non-empty paragraphs
        assert analysis["table_count"] == 1
        assert analysis["has_tables"] is True
        assert analysis["total_characters"] > 0


class TestDOCXParserErrors:
    """Tests for error handling."""

    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        parser = DOCXParser()

        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse("/nonexistent/file.docx")

        assert "DOCX file not found" in str(exc_info.value)

    @patch("doc2json.core.parsers.docx.docx.Document")
    @patch("os.path.exists", return_value=True)
    def test_parse_error_wrapped(self, mock_exists, mock_document):
        """Test that docx errors are wrapped as ParserError."""
        parser = DOCXParser()

        # Create an exception that looks like it came from docx
        class FakeDocxError(Exception):
            pass
        FakeDocxError.__module__ = "docx.opc.exceptions"

        mock_document.side_effect = FakeDocxError("Corrupt file")

        with pytest.raises(ParserError) as exc_info:
            parser.parse("/fake/doc.docx")

        assert "Failed to parse DOCX" in str(exc_info.value)


class TestDOCXParserTableHandling:
    """Tests for table text extraction."""

    def test_merged_cells_deduplication(self):
        """Test that merged cells don't produce duplicate text."""
        parser = DOCXParser()

        # Simulate merged cells (same text appears multiple times)
        mock_cell1 = Mock()
        mock_cell1.text = "Merged"
        mock_cell2 = Mock()
        mock_cell2.text = "Merged"  # Duplicate from merge
        mock_cell3 = Mock()
        mock_cell3.text = "Normal"

        mock_row = Mock()
        mock_row.cells = [mock_cell1, mock_cell2, mock_cell3]

        mock_table = Mock()
        mock_table.rows = [mock_row]

        mock_doc = Mock()
        mock_doc.tables = [mock_table]

        texts = parser._extract_tables(mock_doc)

        # Should only have "Merged" once
        assert len(texts) == 1
        assert texts[0].count("Merged") == 1
        assert "Normal" in texts[0]

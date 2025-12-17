"""Tests for PDF parser."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Skip all tests if PDF dependencies aren't installed
pytest.importorskip("pdfplumber")

from doc2json.core.parsers.pdf import PDFParser, PDFPageResult, MIN_CHARS_PER_PAGE
from doc2json.core.exceptions import ParserError


class TestPDFParserBasics:
    """Basic tests for PDFParser."""

    def test_can_parse_pdf(self):
        """Test that PDF files are recognized."""
        parser = PDFParser()
        assert parser.can_parse("document.pdf") is True
        assert parser.can_parse("path/to/file.PDF") is True
        assert parser.can_parse("/absolute/path/doc.pdf") is True

    def test_cannot_parse_other_types(self):
        """Test that non-PDF files are rejected."""
        parser = PDFParser()
        assert parser.can_parse("document.txt") is False
        assert parser.can_parse("document.docx") is False
        assert parser.can_parse("image.png") is False

    def test_default_settings(self):
        """Test default parser settings."""
        parser = PDFParser()
        assert parser.min_chars_per_page == MIN_CHARS_PER_PAGE
        assert parser.ocr_enabled is True
        assert parser.ocr_language == "eng"

    def test_custom_settings(self):
        """Test custom parser settings."""
        parser = PDFParser(
            min_chars_per_page=100,
            ocr_enabled=False,
            ocr_language="fra",
        )
        assert parser.min_chars_per_page == 100
        assert parser.ocr_enabled is False
        assert parser.ocr_language == "fra"


class TestPDFParserWithMocks:
    """Tests using mocked pdfplumber."""

    @patch("doc2json.core.parsers.pdf.pdfplumber.open")
    @patch("os.path.exists", return_value=True)
    def test_parse_text_based_pdf(self, mock_exists, mock_open):
        """Test parsing a PDF with extractable text."""
        parser = PDFParser()

        # Mock pdfplumber
        mock_page = Mock()
        mock_page.extract_text.return_value = "This is the content of page 1. " * 10

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse("/fake/path.pdf")

        assert "This is the content" in result
        mock_page.extract_text.assert_called_once()

    @patch("doc2json.core.parsers.pdf.pdfplumber.open")
    @patch("os.path.exists", return_value=True)
    def test_parse_multi_page_pdf(self, mock_exists, mock_open):
        """Test parsing a multi-page PDF."""
        parser = PDFParser()

        # Mock pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1 content " * 20

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2 content " * 20

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse("/fake/path.pdf")

        assert "Page 1 content" in result
        assert "Page 2 content" in result

    @patch("doc2json.core.parsers.pdf.pdfplumber.open")
    @patch("os.path.exists", return_value=True)
    def test_parse_empty_page(self, mock_exists, mock_open):
        """Test handling pages with no text."""
        parser = PDFParser(ocr_enabled=False)

        mock_page = Mock()
        mock_page.extract_text.return_value = ""

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse("/fake/path.pdf")

        assert result == ""

    def test_parse_page_result_dataclass(self):
        """Test PDFPageResult dataclass."""
        result = PDFPageResult(page_num=0, text="Hello", used_ocr=False)
        assert result.page_num == 0
        assert result.text == "Hello"
        assert result.used_ocr is False

        ocr_result = PDFPageResult(page_num=1, text="OCR text", used_ocr=True)
        assert ocr_result.used_ocr is True


class TestPDFParserOCRDetection:
    """Tests for image-based PDF detection."""

    def test_detects_low_text_page(self):
        """Test that pages with little text are flagged for OCR."""
        parser = PDFParser(min_chars_per_page=50, ocr_enabled=False)

        mock_page = Mock()
        mock_page.extract_text.return_value = "Short"  # Only 5 chars

        result = parser.parse_page("/fake/path.pdf", mock_page, 0)

        # Should return the text we got, no OCR attempted
        assert result.text == "Short"
        assert result.used_ocr is False

    def test_text_page_not_flagged(self):
        """Test that pages with enough text don't trigger OCR."""
        parser = PDFParser(min_chars_per_page=50)

        mock_page = Mock()
        mock_page.extract_text.return_value = "A" * 100  # 100 chars

        result = parser.parse_page("/fake/path.pdf", mock_page, 0)

        assert result.used_ocr is False
        assert len(result.text) == 100


class TestPDFParserOCRFallback:
    """Tests for OCR fallback functionality."""

    @patch("doc2json.core.parsers.pdf.pytesseract.image_to_string")
    @patch("doc2json.core.parsers.pdf.pdf2image.convert_from_path")
    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_ocr_attempted_for_image_page(self, mock_which, mock_convert, mock_ocr):
        """Test that OCR is attempted for pages with little text."""
        parser = PDFParser(min_chars_per_page=50, ocr_enabled=True)

        # Mock page with little text
        mock_page = Mock()
        mock_page.extract_text.return_value = "X"

        # Mock OCR dependencies
        mock_image = Mock()
        mock_convert.return_value = [mock_image]
        mock_ocr.return_value = "OCR extracted text here"

        result = parser.parse_page("/fake/path.pdf", mock_page, 0)

        assert result.used_ocr is True
        assert "OCR extracted text" in result.text
        mock_convert.assert_called_once()
        mock_ocr.assert_called_once()

    def test_ocr_disabled_skips_ocr(self):
        """Test that OCR is skipped when disabled."""
        parser = PDFParser(min_chars_per_page=50, ocr_enabled=False)

        mock_page = Mock()
        mock_page.extract_text.return_value = "X"  # Below threshold

        result = parser.parse_page("/fake/path.pdf", mock_page, 0)

        assert result.used_ocr is False
        assert result.text == "X"

    @patch("doc2json.core.parsers.pdf.pdf2image.convert_from_path")
    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_ocr_failure_returns_original_text(self, mock_which, mock_convert):
        """Test graceful handling of OCR failures."""
        parser = PDFParser(min_chars_per_page=50, ocr_enabled=True)

        mock_page = Mock()
        mock_page.extract_text.return_value = "Minimal"

        # Mock OCR to fail
        mock_convert.side_effect = Exception("Poppler not found")

        result = parser.parse_page("/fake/path.pdf", mock_page, 0)

        # Should return original text when OCR fails
        assert result.text == "Minimal"
        assert result.used_ocr is False


class TestPDFParserAnalyze:
    """Tests for PDF analysis functionality."""

    @patch("doc2json.core.parsers.pdf.pdfplumber.open")
    def test_analyze_text_pdf(self, mock_open):
        """Test analyzing a text-based PDF."""
        parser = PDFParser(min_chars_per_page=50)

        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "A" * 100

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "B" * 200

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)
        mock_open.return_value = mock_pdf

        analysis = parser.analyze("/fake/path.pdf")

        assert analysis["total_pages"] == 2
        assert analysis["text_pages"] == 2
        assert analysis["image_pages"] == 0
        assert analysis["total_characters"] == 300
        assert analysis["avg_chars_per_page"] == 150
        assert analysis["likely_scanned"] is False
        assert analysis["ocr_recommended"] is False

    @patch("doc2json.core.parsers.pdf.pdfplumber.open")
    def test_analyze_scanned_pdf(self, mock_open):
        """Test analyzing a scanned PDF."""
        parser = PDFParser(min_chars_per_page=50)

        mock_page1 = Mock()
        mock_page1.extract_text.return_value = ""  # No text

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "X"  # Minimal text

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)
        mock_open.return_value = mock_pdf

        analysis = parser.analyze("/fake/path.pdf")

        assert analysis["total_pages"] == 2
        assert analysis["text_pages"] == 0
        assert analysis["image_pages"] == 2
        assert analysis["likely_scanned"] is True
        assert analysis["ocr_recommended"] is True


class TestPDFParserErrors:
    """Tests for error handling."""

    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        parser = PDFParser()

        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse("/nonexistent/file.pdf")

        assert "PDF file not found" in str(exc_info.value)

    def test_missing_tesseract_error(self):
        """Test error message when Tesseract is not installed."""
        parser = PDFParser(ocr_enabled=True)

        # Mock shutil.which to return None (Tesseract not found)
        with patch("shutil.which", return_value=None):
            with pytest.raises(ParserError) as exc_info:
                parser._check_tesseract()

            assert "Tesseract" in str(exc_info.value)


class TestPDFParserIntegration:
    """Integration tests that would use real PDF files.

    These tests are skipped by default - enable them by providing
    test PDF files in tests/fixtures/
    """

    @pytest.fixture
    def text_pdf_path(self, tmp_path):
        """Path to a text-based test PDF."""
        # Would need to create or provide a real PDF
        return None

    @pytest.fixture
    def scanned_pdf_path(self, tmp_path):
        """Path to a scanned test PDF."""
        # Would need to create or provide a real PDF
        return None

    @pytest.mark.skip(reason="Requires real PDF test files")
    def test_parse_real_text_pdf(self, text_pdf_path):
        """Test parsing a real text-based PDF."""
        if text_pdf_path is None:
            pytest.skip("No test PDF available")

        parser = PDFParser()
        text = parser.parse(str(text_pdf_path))
        assert len(text) > 0

    @pytest.mark.skip(reason="Requires real PDF test files and Tesseract")
    def test_parse_real_scanned_pdf(self, scanned_pdf_path):
        """Test parsing a real scanned PDF with OCR."""
        if scanned_pdf_path is None:
            pytest.skip("No test PDF available")

        parser = PDFParser(ocr_enabled=True)
        text = parser.parse(str(scanned_pdf_path))
        assert len(text) > 0

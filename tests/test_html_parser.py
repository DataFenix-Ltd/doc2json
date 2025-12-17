"""Tests for HTML parser.

Note: These tests require the HTML dependencies to be installed:
    pip install doc2json[html]
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

# Skip all tests if HTML dependencies aren't installed
pytest.importorskip("bs4")

from doc2json.core.parsers.html import HTMLParser, HTMLExtractor
from doc2json.core.exceptions import ParserError


class TestHTMLParserBasics:
    """Basic tests for HTMLParser."""

    def test_can_parse_html(self):
        """Test that HTML files are recognized."""
        parser = HTMLParser()
        assert parser.can_parse("page.html") is True
        assert parser.can_parse("page.htm") is True
        assert parser.can_parse("path/to/file.HTML") is True
        assert parser.can_parse("/absolute/path/doc.htm") is True

    def test_cannot_parse_other_types(self):
        """Test that non-HTML files are rejected."""
        parser = HTMLParser()
        assert parser.can_parse("document.txt") is False
        assert parser.can_parse("document.xml") is False
        assert parser.can_parse("document.pdf") is False

    def test_default_settings(self):
        """Test default parser settings."""
        parser = HTMLParser()
        assert parser.extractor.preserve_links is False
        assert parser.extractor.preserve_images is False

    def test_custom_settings(self):
        """Test custom parser settings."""
        parser = HTMLParser(preserve_links=True, preserve_images=True)
        assert parser.extractor.preserve_links is True
        assert parser.extractor.preserve_images is True


class TestHTMLExtractor:
    """Tests for HTMLExtractor (raw HTML processing)."""

    def test_extract_simple_html(self):
        """Test extracting text from simple HTML."""
        extractor = HTMLExtractor()
        html = "<html><body><p>Hello World</p></body></html>"

        result = extractor.extract(html)

        assert "Hello World" in result

    def test_extract_multiple_paragraphs(self):
        """Test extracting multiple paragraphs."""
        extractor = HTMLExtractor()
        html = """
        <html><body>
            <p>First paragraph</p>
            <p>Second paragraph</p>
        </body></html>
        """

        result = extractor.extract(html)

        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_removes_script_tags(self):
        """Test that script content is removed."""
        extractor = HTMLExtractor()
        html = """
        <html><body>
            <p>Visible text</p>
            <script>alert('hidden');</script>
        </body></html>
        """

        result = extractor.extract(html)

        assert "Visible text" in result
        assert "alert" not in result
        assert "hidden" not in result

    def test_removes_style_tags(self):
        """Test that style content is removed."""
        extractor = HTMLExtractor()
        html = """
        <html><body>
            <p>Visible text</p>
            <style>.hidden { display: none; }</style>
        </body></html>
        """

        result = extractor.extract(html)

        assert "Visible text" in result
        assert "display" not in result

    def test_removes_nav_and_footer(self):
        """Test that navigation and footer are removed."""
        extractor = HTMLExtractor()
        html = """
        <html><body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <main><p>Main content here</p></main>
            <footer>Copyright 2024</footer>
        </body></html>
        """

        result = extractor.extract(html)

        assert "Main content" in result
        assert "Home" not in result
        assert "Copyright" not in result

    def test_preserve_links(self):
        """Test preserving link URLs."""
        extractor = HTMLExtractor(preserve_links=True)
        html = '<p>Visit <a href="https://example.com">our site</a></p>'

        result = extractor.extract(html)

        assert "our site" in result
        assert "https://example.com" in result

    def test_preserve_images(self):
        """Test preserving image alt text."""
        extractor = HTMLExtractor(preserve_images=True)
        html = '<p>Look at this: <img src="cat.jpg" alt="A cute cat"></p>'

        result = extractor.extract(html)

        assert "[Image: A cute cat]" in result

    def test_handles_tables(self):
        """Test extracting text from tables."""
        extractor = HTMLExtractor()
        html = """
        <table>
            <tr><th>Name</th><th>Value</th></tr>
            <tr><td>Item 1</td><td>100</td></tr>
        </table>
        """

        result = extractor.extract(html)

        assert "Name" in result
        assert "Item 1" in result
        assert "100" in result

    def test_handles_lists(self):
        """Test extracting text from lists."""
        extractor = HTMLExtractor()
        html = """
        <ul>
            <li>First item</li>
            <li>Second item</li>
        </ul>
        """

        result = extractor.extract(html)

        assert "First item" in result
        assert "Second item" in result

    def test_extract_structured(self):
        """Test structured extraction."""
        extractor = HTMLExtractor()
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Main Heading</h1>
            <h2>Subheading</h2>
            <p>First paragraph</p>
            <p>Second paragraph</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
        </html>
        """

        result = extractor.extract_structured(html)

        assert result["title"] == "Test Page"
        assert len(result["headings"]) == 2
        assert result["headings"][0]["level"] == 1
        assert result["headings"][0]["text"] == "Main Heading"
        assert len(result["paragraphs"]) == 2
        assert len(result["lists"]) == 1
        assert len(result["lists"][0]) == 2

    def test_extract_structured_tables(self):
        """Test structured extraction of tables."""
        extractor = HTMLExtractor()
        html = """
        <table>
            <tr><th>A</th><th>B</th></tr>
            <tr><td>1</td><td>2</td></tr>
        </table>
        """

        result = extractor.extract_structured(html)

        assert len(result["tables"]) == 1
        assert result["tables"][0] == [["A", "B"], ["1", "2"]]


class TestHTMLParserFile:
    """Tests for file-based HTML parsing."""

    def test_parse_file(self, tmp_path):
        """Test parsing an HTML file."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<html><body><p>File content</p></body></html>")

        parser = HTMLParser()
        result = parser.parse(str(html_file))

        assert "File content" in result

    def test_parse_file_utf8(self, tmp_path):
        """Test parsing UTF-8 HTML file."""
        html_file = tmp_path / "test.html"
        html_file.write_text(
            '<html><head><meta charset="utf-8"></head>'
            '<body><p>Café résumé</p></body></html>',
            encoding="utf-8"
        )

        parser = HTMLParser()
        result = parser.parse(str(html_file))

        assert "Café" in result
        assert "résumé" in result

    def test_parse_file_not_found(self):
        """Test error when file doesn't exist."""
        parser = HTMLParser()

        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse("/nonexistent/file.html")

        assert "HTML file not found" in str(exc_info.value)

    def test_analyze_file(self, tmp_path):
        """Test analyzing an HTML file."""
        html_file = tmp_path / "test.html"
        html_file.write_text("""
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Heading</h1>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </body>
        </html>
        """)

        parser = HTMLParser()
        analysis = parser.analyze(str(html_file))

        assert analysis["title"] == "Test"
        assert analysis["heading_count"] == 1
        assert analysis["paragraph_count"] == 2
        assert analysis["has_content"] is True


class TestHTMLParserEncoding:
    """Tests for encoding detection."""

    def test_detect_utf8_bom(self, tmp_path):
        """Test detecting UTF-8 BOM."""
        html_file = tmp_path / "test.html"
        # Write with BOM
        with open(html_file, "wb") as f:
            f.write(b"\xef\xbb\xbf<html><body>Test</body></html>")

        parser = HTMLParser()
        encoding = parser._detect_encoding(str(html_file))

        assert encoding == "utf-8-sig"

    def test_detect_charset_meta(self, tmp_path):
        """Test detecting charset from meta tag."""
        html_file = tmp_path / "test.html"
        html_file.write_bytes(
            b'<html><head><meta charset="utf-8"></head></html>'
        )

        parser = HTMLParser()
        encoding = parser._detect_encoding(str(html_file))

        assert encoding == "utf-8"

    def test_fallback_to_utf8(self, tmp_path):
        """Test fallback to UTF-8 when no encoding detected."""
        html_file = tmp_path / "test.html"
        html_file.write_bytes(b"<html><body>Simple</body></html>")

        parser = HTMLParser()
        encoding = parser._detect_encoding(str(html_file))

        assert encoding == "utf-8"


class TestHTMLExtractorEdgeCases:
    """Tests for edge cases in HTML extraction."""

    def test_empty_html(self):
        """Test handling empty HTML."""
        extractor = HTMLExtractor()
        result = extractor.extract("")
        assert result == ""

    def test_only_whitespace(self):
        """Test handling HTML with only whitespace."""
        extractor = HTMLExtractor()
        result = extractor.extract("<html><body>   \n\t  </body></html>")
        assert result == ""

    def test_malformed_html(self):
        """Test handling malformed HTML."""
        extractor = HTMLExtractor()
        html = "<p>Unclosed paragraph<div>Mixed content</p></div>"

        # Should not raise, BeautifulSoup handles malformed HTML
        result = extractor.extract(html)
        assert "Unclosed paragraph" in result
        assert "Mixed content" in result

    def test_nested_removed_tags(self):
        """Test that nested removed tags are fully removed."""
        extractor = HTMLExtractor()
        html = """
        <nav>
            <div>
                <script>nested()</script>
                <a href="/">Link</a>
            </div>
        </nav>
        <p>Content</p>
        """

        result = extractor.extract(html)

        assert "Content" in result
        assert "Link" not in result
        assert "nested" not in result

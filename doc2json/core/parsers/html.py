"""HTML document parser for local files and raw HTML content.

This module is designed to work both as a file parser and as a utility
for future web scraping functionality. The HTMLExtractor class can
process raw HTML strings, while HTMLParser wraps it for file-based use.
"""

import logging
import os
from typing import Optional

from bs4 import BeautifulSoup

from doc2json.core.exceptions import ParserError

logger = logging.getLogger(__name__)

# Tags to remove entirely (content and all)
REMOVE_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "meta", "link", "header", "footer", "nav", "aside",
    "form", "button", "input", "select", "textarea",
}

# Tags to remove for text extraction but preserve for structured extraction
REMOVE_TAGS_TEXT_ONLY = {"head"}

# Tags that should add newlines for readability
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "h1", "h2", "h3",
    "h4", "h5", "h6", "li", "tr", "br", "hr", "blockquote", "pre",
}


class HTMLExtractor:
    """Extract clean text from HTML content.

    This class handles the actual HTML parsing and text extraction.
    It can be used directly with raw HTML strings, making it suitable
    for both file parsing and web scraping use cases.

    Example:
        # Direct usage with HTML string
        extractor = HTMLExtractor()
        text = extractor.extract("<html><body><p>Hello</p></body></html>")

        # For web scraping (future use)
        html = requests.get(url).text
        text = extractor.extract(html)
    """

    def __init__(
        self,
        remove_tags: Optional[set[str]] = None,
        preserve_links: bool = False,
        preserve_images: bool = False,
    ):
        """Initialize HTML extractor.

        Args:
            remove_tags: Additional tags to remove (merged with defaults)
            preserve_links: Include link URLs in output (default False)
            preserve_images: Include image alt text in output (default False)
        """
        self.remove_tags = REMOVE_TAGS.copy()
        if remove_tags:
            self.remove_tags.update(remove_tags)
        self.preserve_links = preserve_links
        self.preserve_images = preserve_images

    def extract(self, html: str, parser: str = "lxml") -> str:
        """Extract clean text from HTML content.

        Args:
            html: Raw HTML string
            parser: BeautifulSoup parser to use ('lxml', 'html.parser', etc.)

        Returns:
            Cleaned text content
        """
        try:
            soup = BeautifulSoup(html, parser)
        except Exception:
            # Fall back to built-in parser if lxml not available
            soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags entirely
        for tag in self.remove_tags:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove head tag for text extraction (but not for structured)
        for tag in REMOVE_TAGS_TEXT_ONLY:
            for element in soup.find_all(tag):
                element.decompose()

        # Handle links if preserving
        if self.preserve_links:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if href and not href.startswith("#"):
                    a.replace_with(f"{a.get_text()} ({href})")

        # Handle images if preserving alt text
        if self.preserve_images:
            for img in soup.find_all("img", alt=True):
                alt = img.get("alt", "").strip()
                if alt:
                    img.replace_with(f"[Image: {alt}]")

        # Extract text with separator for block elements
        text = soup.get_text(separator="\n", strip=True)

        # Clean up excessive newlines
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        return "\n\n".join(self._merge_short_lines(lines))

    def _merge_short_lines(self, lines: list[str], threshold: int = 40) -> list[str]:
        """Merge very short consecutive lines that are likely part of the same paragraph."""
        if not lines:
            return lines

        result = []
        current = lines[0]

        for line in lines[1:]:
            # If current line is short and next doesn't look like a heading
            if (len(current) < threshold and
                not current.endswith((".", "!", "?", ":")) and
                not line[0].isupper() if line else False):
                current = f"{current} {line}"
            else:
                result.append(current)
                current = line

        result.append(current)
        return result

    def extract_structured(self, html: str, parser: str = "lxml") -> dict:
        """Extract text with some structure preserved.

        Returns a dict with title, headings, and body text separated.
        Useful for more sophisticated extraction needs.
        """
        try:
            soup = BeautifulSoup(html, parser)
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags
        for tag in self.remove_tags:
            for element in soup.find_all(tag):
                element.decompose()

        result = {
            "title": "",
            "headings": [],
            "paragraphs": [],
            "tables": [],
            "lists": [],
        }

        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # Also check for h1 if no title
        if not result["title"]:
            h1 = soup.find("h1")
            if h1:
                result["title"] = h1.get_text(strip=True)

        # Extract headings
        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                if text:
                    result["headings"].append({
                        "level": level,
                        "text": text,
                    })

        # Extract paragraphs
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                result["paragraphs"].append(text)

        # Extract tables
        for table in soup.find_all("table"):
            table_data = []
            for row in table.find_all("tr"):
                cells = []
                for cell in row.find_all(["td", "th"]):
                    cells.append(cell.get_text(strip=True))
                if cells:
                    table_data.append(cells)
            if table_data:
                result["tables"].append(table_data)

        # Extract lists
        for ul in soup.find_all(["ul", "ol"]):
            items = []
            for li in ul.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    items.append(text)
            if items:
                result["lists"].append(items)

        return result


class HTMLParser:
    """Parser for local HTML files.

    Wraps HTMLExtractor for file-based parsing, following the
    DocumentParser protocol used by the parser registry.
    """

    SUPPORTED_EXTENSIONS = {".html", ".htm"}

    def __init__(
        self,
        preserve_links: bool = False,
        preserve_images: bool = False,
    ):
        """Initialize HTML parser.

        Args:
            preserve_links: Include link URLs in output
            preserve_images: Include image alt text in output
        """
        self.extractor = HTMLExtractor(
            preserve_links=preserve_links,
            preserve_images=preserve_images,
        )

    def can_parse(self, file_path: str) -> bool:
        """Check if this is an HTML file."""
        _, ext = os.path.splitext(file_path)
        return ext.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str) -> str:
        """Parse an HTML file and extract text."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        # Detect encoding
        encoding = self._detect_encoding(file_path)

        try:
            with open(file_path, "r", encoding=encoding) as f:
                html = f.read()
            return self.extractor.extract(html)
        except UnicodeDecodeError:
            # Fallback to latin-1 which accepts any byte
            with open(file_path, "r", encoding="latin-1") as f:
                html = f.read()
            return self.extractor.extract(html)

    def _detect_encoding(self, file_path: str) -> str:
        """Detect file encoding from HTML meta tag or BOM."""
        # Read first 1KB to check for encoding hints
        with open(file_path, "rb") as f:
            head = f.read(1024)

        # Check for BOM
        if head.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if head.startswith(b"\xff\xfe"):
            return "utf-16-le"
        if head.startswith(b"\xfe\xff"):
            return "utf-16-be"

        # Look for charset in meta tag
        head_str = head.decode("ascii", errors="ignore").lower()
        if 'charset="utf-8"' in head_str or "charset=utf-8" in head_str:
            return "utf-8"
        if 'charset="iso-8859-1"' in head_str or "charset=iso-8859-1" in head_str:
            return "iso-8859-1"
        if 'charset="windows-1252"' in head_str or "charset=windows-1252" in head_str:
            return "windows-1252"

        return "utf-8"

    def parse_structured(self, file_path: str) -> dict:
        """Parse an HTML file and return structured content."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        encoding = self._detect_encoding(file_path)

        with open(file_path, "r", encoding=encoding) as f:
            html = f.read()

        return self.extractor.extract_structured(html)

    def analyze(self, file_path: str) -> dict:
        """Analyze an HTML file structure."""
        structured = self.parse_structured(file_path)

        return {
            "title": structured["title"],
            "heading_count": len(structured["headings"]),
            "paragraph_count": len(structured["paragraphs"]),
            "table_count": len(structured["tables"]),
            "list_count": len(structured["lists"]),
            "has_content": bool(structured["paragraphs"] or structured["tables"]),
        }

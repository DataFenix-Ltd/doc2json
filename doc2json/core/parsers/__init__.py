from typing import Protocol
import os

from doc2json.core.exceptions import UnsupportedFileTypeError


class DocumentParser(Protocol):
    """Protocol for document parsers that extract text from files."""

    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can handle the given file."""
        ...

    def parse(self, file_path: str) -> str:
        """Extract text content from the file."""
        ...


class ParserRegistry:
    """Registry that selects the appropriate parser for a file."""

    def __init__(self):
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        """Register a parser with the registry."""
        self._parsers.append(parser)

    def get_parser(self, file_path: str) -> DocumentParser:
        """Get the appropriate parser for a file.

        Raises:
            UnsupportedFileTypeError: If no parser can handle the file
        """
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser

        _, ext = os.path.splitext(file_path)
        supported = self._get_supported_extensions()
        raise UnsupportedFileTypeError(
            f"No parser available for '{ext}' files. "
            f"Supported formats: {', '.join(sorted(supported)) or 'none registered'}"
        )

    def _get_supported_extensions(self) -> set[str]:
        """Get all supported file extensions from registered parsers."""
        extensions = set()
        for parser in self._parsers:
            if hasattr(parser, "SUPPORTED_EXTENSIONS"):
                extensions.update(parser.SUPPORTED_EXTENSIONS)
        return extensions

    def parse(self, file_path: str) -> str:
        """Parse a file using the appropriate parser."""
        parser = self.get_parser(file_path)
        return parser.parse(file_path)


# Global registry instance
_registry = ParserRegistry()


def register_parser(parser: DocumentParser) -> None:
    """Register a parser with the global registry."""
    _registry.register(parser)


def parse_document(file_path: str) -> str:
    """Parse a document using the global registry."""
    return _registry.parse(file_path)


def get_registry() -> ParserRegistry:
    """Get the global parser registry."""
    return _registry


# Register all built-in parsers
from doc2json.core.parsers.text import TextParser
from doc2json.core.parsers.pdf import PDFParser
from doc2json.core.parsers.docx import DOCXParser
from doc2json.core.parsers.html import HTMLParser

register_parser(TextParser())
register_parser(PDFParser())
register_parser(DOCXParser())
register_parser(HTMLParser())

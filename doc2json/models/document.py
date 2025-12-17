"""Document metadata and size information."""

from dataclasses import dataclass
from typing import Optional


# Thresholds for document size classification
LARGE_DOC_CHARS = 30_000  # ~7.5k tokens
LARGE_DOC_PAGES = 20
MAX_CHARS_DEFAULT = 100_000  # ~25k tokens - default limit for extraction


@dataclass
class DocumentInfo:
    """Metadata about a parsed document.

    Used to determine extraction strategy for large documents.
    """
    file_path: str
    char_count: int
    page_count: Optional[int] = None  # None for non-paginated formats (txt, html)

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (chars / 4)."""
        return self.char_count // 4

    @property
    def is_large(self) -> bool:
        """Check if document exceeds 'large' thresholds."""
        if self.char_count > LARGE_DOC_CHARS:
            return True
        if self.page_count and self.page_count > LARGE_DOC_PAGES:
            return True
        return False

    def exceeds_limit(self, max_chars: int) -> bool:
        """Check if document exceeds a specific character limit."""
        return self.char_count > max_chars

    def __str__(self) -> str:
        pages = f", {self.page_count} pages" if self.page_count else ""
        return f"DocumentInfo({self.char_count:,} chars{pages}, ~{self.estimated_tokens:,} tokens)"

"""Custom exceptions for doc2json."""


class Doc2JsonError(Exception):
    """Base exception for all doc2json errors."""
    pass


class ConfigError(Doc2JsonError):
    """Configuration-related errors."""
    pass


class SchemaError(Doc2JsonError):
    """Schema loading and validation errors."""
    pass


class SchemaNotFoundError(SchemaError):
    """Schema file not found."""
    pass


class SchemaValidationError(SchemaError):
    """Schema definition is invalid."""
    pass


class ParserError(Doc2JsonError):
    """Document parsing errors."""
    pass


class UnsupportedFileTypeError(ParserError):
    """No parser available for file type."""
    pass


class ExtractionError(Doc2JsonError):
    """Extraction-related errors."""
    pass


class ProviderError(ExtractionError):
    """LLM provider configuration errors."""
    pass


class APIError(ExtractionError):
    """LLM API call errors."""

    def __init__(self, message: str, provider: str, original_error: Exception | None = None):
        self.provider = provider
        self.original_error = original_error
        super().__init__(message)


class RateLimitError(APIError):
    """Rate limit exceeded."""
    pass


class AuthenticationError(APIError):
    """Authentication failed (invalid API key)."""
    pass


class ValidationError(ExtractionError):
    """LLM response failed schema validation."""

    def __init__(self, message: str, schema_name: str | None = None):
        self.schema_name = schema_name
        super().__init__(message)


class DocumentTooLargeError(ParserError):
    """Document exceeds size limits for extraction."""

    def __init__(self, message: str, char_count: int, max_chars: int):
        self.char_count = char_count
        self.max_chars = max_chars
        super().__init__(message)


class EmptyDocumentError(ParserError):
    """Document has no extractable content."""

    def __init__(self, message: str, file_path: str):
        self.file_path = file_path
        super().__init__(message)

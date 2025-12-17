"""Metadata models for pipeline observability."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ExtractionMetadata:
    """Metadata for a single file extraction."""
    source_file: str
    started_at: datetime
    completed_at: datetime
    success: bool

    # Document info
    char_count: int
    page_count: Optional[int] = None
    truncated: bool = False

    # LLM config (for traceability)
    provider: str = ""
    model: str = ""

    # LLM usage
    extract_tokens: Optional[TokenUsage] = None
    assess_tokens: Optional[TokenUsage] = None

    # Error info
    error: Optional[str] = None

    @property
    def duration_ms(self) -> int:
        """Duration in milliseconds."""
        delta = self.completed_at - self.started_at
        return int(delta.total_seconds() * 1000)

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all LLM calls."""
        total = 0
        if self.extract_tokens:
            total += self.extract_tokens.total_tokens
        if self.assess_tokens:
            total += self.assess_tokens.total_tokens
        return total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSONL output."""
        result = {
            "source_file": self.source_file,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "char_count": self.char_count,
            "truncated": self.truncated,
        }

        if self.page_count is not None:
            result["page_count"] = self.page_count

        # LLM config
        if self.provider:
            result["provider"] = self.provider
        if self.model:
            result["model"] = self.model

        if self.extract_tokens:
            result["extract_tokens"] = {
                "input": self.extract_tokens.input_tokens,
                "output": self.extract_tokens.output_tokens,
            }

        if self.assess_tokens:
            result["assess_tokens"] = {
                "input": self.assess_tokens.input_tokens,
                "output": self.assess_tokens.output_tokens,
            }

        result["total_tokens"] = self.total_tokens

        if self.error:
            result["error"] = self.error

        return result


@dataclass
class RunMetadata:
    """Metadata for a complete pipeline run."""
    schema_name: str
    schema_version: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    # LLM config
    provider: str = ""
    model: str = ""

    # Aggregates
    files_processed: int = 0
    files_succeeded: int = 0
    files_failed: int = 0

    # Per-file metadata
    extractions: list[ExtractionMetadata] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        """Duration in milliseconds."""
        if not self.completed_at:
            return 0
        delta = self.completed_at - self.started_at
        return int(delta.total_seconds() * 1000)

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all extractions."""
        return sum(e.total_tokens for e in self.extractions)

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens across all extractions."""
        total = 0
        for e in self.extractions:
            if e.extract_tokens:
                total += e.extract_tokens.input_tokens
            if e.assess_tokens:
                total += e.assess_tokens.input_tokens
        return total

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens across all extractions."""
        total = 0
        for e in self.extractions:
            if e.extract_tokens:
                total += e.extract_tokens.output_tokens
            if e.assess_tokens:
                total += e.assess_tokens.output_tokens
        return total

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to summary dictionary for the run header."""
        result = {
            "_type": "run_summary",
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "started_at": self.started_at.isoformat(),
            "files_processed": self.files_processed,
            "files_succeeded": self.files_succeeded,
            "files_failed": self.files_failed,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
        }

        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
            result["duration_ms"] = self.duration_ms

        return result

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    """Review status for an extraction result."""
    NEEDS_REVIEW = "needs_review"           # Significant issues detected
    SUGGESTED_REVIEW = "suggested_review"   # Minor ambiguities, review recommended
    NO_REVIEW_NEEDED = "no_review_needed"   # High quality extraction


class FieldSuggestion(BaseModel):
    """A suggested field to add to the schema."""

    name: str = Field(description="Snake_case field name")
    field_type: str = Field(description="Python type (str, int, float, bool, list[str], Optional[str], etc.)")
    description: str = Field(description="Short description for the Field() descriptor")
    sample_value: Optional[str] = Field(
        default=None,
        description="Example value from the document (if available)"
    )


class Assessment(BaseModel):
    """Assessment of an extraction result's quality and completeness."""

    review_status: ReviewStatus = Field(
        description="Overall review status for this extraction"
    )
    ambiguous_fields: list[str] = Field(
        default_factory=list,
        description="List of field names where the extraction was uncertain or ambiguous"
    )
    review_notes: str = Field(
        default="",
        description="Explanation of any issues or ambiguities found"
    )
    schema_suggestions: list[FieldSuggestion] = Field(
        default_factory=list,
        description="Suggested fields to add to the schema based on this document"
    )


class ExtractionResult(BaseModel):
    """Wrapper for extraction results with optional assessment."""

    source_file: str = Field(description="Name of the source file")
    schema_name: str = Field(description="Name of the schema used")
    schema_version: str = Field(description="Version of the schema used")
    data: dict[str, Any] = Field(description="The extracted data")
    assessment: Optional[Assessment] = Field(
        default=None,
        description="Quality assessment (if assess=true in config)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if extraction failed"
    )
    truncated: bool = Field(
        default=False,
        description="Whether the document was truncated due to size limits"
    )
    original_chars: Optional[int] = Field(
        default=None,
        description="Original character count if document was truncated"
    )

    def to_output_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSONL output."""
        result = {
            "_source_file": self.source_file,
            "_schema": self.schema_name,
            "_schema_version": self.schema_version,
        }

        if self.error:
            result["_error"] = self.error
            return result

        # Add extracted data
        result.update(self.data)

        # Add truncation warning if applicable
        if self.truncated:
            result["_truncated"] = True
            result["_original_chars"] = self.original_chars

        # Add assessment if present
        if self.assessment:
            result["_assessment"] = {
                "review_status": self.assessment.review_status.value,
                "ambiguous_fields": self.assessment.ambiguous_fields,
                "review_notes": self.assessment.review_notes,
                "schema_suggestions": [s.model_dump() for s in self.assessment.schema_suggestions],
            }

        return result

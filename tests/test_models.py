"""Tests for data models."""

import pytest

from doc2json.models.result import (
    ReviewStatus,
    Assessment,
    ExtractionResult,
    FieldSuggestion,
)


class TestReviewStatus:
    """Tests for ReviewStatus enum."""

    def test_enum_values(self):
        """Test that all expected status values exist."""
        assert ReviewStatus.NEEDS_REVIEW.value == "needs_review"
        assert ReviewStatus.SUGGESTED_REVIEW.value == "suggested_review"
        assert ReviewStatus.NO_REVIEW_NEEDED.value == "no_review_needed"

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        status = ReviewStatus("needs_review")
        assert status == ReviewStatus.NEEDS_REVIEW


class TestAssessment:
    """Tests for Assessment model."""

    def test_minimal_assessment(self):
        """Test creating assessment with minimal fields."""
        assessment = Assessment(review_status=ReviewStatus.NO_REVIEW_NEEDED)

        assert assessment.review_status == ReviewStatus.NO_REVIEW_NEEDED
        assert assessment.ambiguous_fields == []
        assert assessment.review_notes == ""
        assert assessment.schema_suggestions == []

    def test_full_assessment(self):
        """Test creating assessment with all fields."""
        assessment = Assessment(
            review_status=ReviewStatus.NEEDS_REVIEW,
            ambiguous_fields=["date", "amount"],
            review_notes="Date format unclear, amount may be in different currency.",
            schema_suggestions=[
                FieldSuggestion(name="currency", field_type="Optional[str]", description="Currency code"),
                FieldSuggestion(name="date_format", field_type="Optional[str]", description="Date format used"),
            ],
        )

        assert assessment.review_status == ReviewStatus.NEEDS_REVIEW
        assert len(assessment.ambiguous_fields) == 2
        assert "date" in assessment.ambiguous_fields
        assert len(assessment.schema_suggestions) == 2

    def test_assessment_serialization(self):
        """Test assessment serializes to dict correctly."""
        assessment = Assessment(
            review_status=ReviewStatus.SUGGESTED_REVIEW,
            ambiguous_fields=["title"],
            review_notes="Title truncated.",
        )

        data = assessment.model_dump()
        assert data["review_status"] == ReviewStatus.SUGGESTED_REVIEW
        assert data["ambiguous_fields"] == ["title"]


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    def test_successful_result(self):
        """Test creating a successful extraction result."""
        result = ExtractionResult(
            source_file="invoice.txt",
            schema_name="invoice",
            schema_version="1",
            data={"title": "Invoice #123", "amount": 100.00},
        )

        assert result.source_file == "invoice.txt"
        assert result.schema_name == "invoice"
        assert result.schema_version == "1"
        assert result.data["title"] == "Invoice #123"
        assert result.assessment is None
        assert result.error is None

    def test_result_with_assessment(self):
        """Test result with assessment attached."""
        assessment = Assessment(review_status=ReviewStatus.NO_REVIEW_NEEDED)
        result = ExtractionResult(
            source_file="doc.txt",
            schema_name="test",
            schema_version="1",
            data={"title": "Test"},
            assessment=assessment,
        )

        assert result.assessment is not None
        assert result.assessment.review_status == ReviewStatus.NO_REVIEW_NEEDED

    def test_result_with_error(self):
        """Test result with error."""
        result = ExtractionResult(
            source_file="bad.txt",
            schema_name="test",
            schema_version="1",
            data={},
            error="Failed to parse document",
        )

        assert result.error == "Failed to parse document"

    def test_to_output_dict_success(self):
        """Test to_output_dict for successful extraction."""
        result = ExtractionResult(
            source_file="invoice.txt",
            schema_name="invoice",
            schema_version="2",
            data={"title": "Invoice", "amount": 500.00},
        )

        output = result.to_output_dict()

        assert output["_source_file"] == "invoice.txt"
        assert output["_schema"] == "invoice"
        assert output["_schema_version"] == "2"
        assert output["title"] == "Invoice"
        assert output["amount"] == 500.00
        assert "_error" not in output
        assert "_assessment" not in output

    def test_to_output_dict_with_assessment(self):
        """Test to_output_dict includes assessment when present."""
        assessment = Assessment(
            review_status=ReviewStatus.SUGGESTED_REVIEW,
            ambiguous_fields=["date"],
            review_notes="Date format unclear",
            schema_suggestions=[
                FieldSuggestion(name="date_format", field_type="Optional[str]", description="Date format used"),
            ],
        )
        result = ExtractionResult(
            source_file="doc.txt",
            schema_name="test",
            schema_version="1",
            data={"title": "Test"},
            assessment=assessment,
        )

        output = result.to_output_dict()

        assert "_assessment" in output
        assert output["_assessment"]["review_status"] == "suggested_review"
        assert output["_assessment"]["ambiguous_fields"] == ["date"]

    def test_to_output_dict_with_error(self):
        """Test to_output_dict for failed extraction."""
        result = ExtractionResult(
            source_file="bad.txt",
            schema_name="test",
            schema_version="1",
            data={},
            error="API timeout",
        )

        output = result.to_output_dict()

        assert output["_source_file"] == "bad.txt"
        assert output["_error"] == "API timeout"
        # Data fields should not be present when there's an error
        assert "title" not in output

    def test_data_fields_merged_into_output(self):
        """Test that data fields are merged at top level of output."""
        result = ExtractionResult(
            source_file="doc.txt",
            schema_name="complex",
            schema_version="1",
            data={
                "title": "Document",
                "items": [{"name": "Item 1"}, {"name": "Item 2"}],
                "metadata": {"author": "John"},
            },
        )

        output = result.to_output_dict()

        # Data should be merged at top level
        assert output["title"] == "Document"
        assert output["items"] == [{"name": "Item 1"}, {"name": "Item 2"}]
        assert output["metadata"] == {"author": "John"}

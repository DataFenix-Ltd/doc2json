"""Tests for extraction engine with mocked LLM responses."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import BaseModel, Field
from typing import Optional

from doc2json.core.extraction import ExtractionEngine
from doc2json.models.result import Assessment, ReviewStatus, FieldSuggestion
from doc2json.core.exceptions import (
    ProviderError,
    APIError,
    RateLimitError,
    AuthenticationError,
)


class InvoiceSchema(BaseModel):
    """Test schema for extraction tests."""
    title: str = Field(description="Invoice title or number")
    amount: Optional[float] = Field(default=None, description="Total amount")
    date: Optional[str] = Field(default=None, description="Invoice date")


class TestExtractionEngine:
    """Tests for ExtractionEngine class."""

    def test_init_default_provider(self):
        """Test default initialization."""
        engine = ExtractionEngine()
        assert engine.provider == "anthropic"
        assert engine.model == "claude-sonnet-4-20250514"
        assert engine._client is None

    def test_init_custom_provider(self):
        """Test initialization with custom provider."""
        engine = ExtractionEngine(provider="openai", model="gpt-4o")
        assert engine.provider == "openai"
        assert engine.model == "gpt-4o"

    def test_unsupported_provider(self):
        """Test error for unsupported provider."""
        engine = ExtractionEngine(provider="unsupported", model="model")

        with pytest.raises(ProviderError) as exc_info:
            engine._get_client()

        assert "Unsupported LLM provider" in str(exc_info.value)
        assert "unsupported" in str(exc_info.value)

    def test_client_cached(self):
        """Test that client is only created once."""
        engine = ExtractionEngine()
        engine._client = Mock()  # Pre-set client

        client1 = engine._get_client()
        client2 = engine._get_client()

        assert client1 is client2


class TestExtractionEngineWithMocks:
    """Tests for ExtractionEngine with mocked LLM clients."""

    def test_extract_anthropic(self):
        """Test extraction with Anthropic provider using pre-set mock client."""
        engine = ExtractionEngine(provider="anthropic")

        # Create mock client that returns expected schema
        # create_with_completion returns (model, completion) tuple
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create_with_completion.return_value = (
            InvoiceSchema(
                title="Invoice #123",
                amount=500.00,
                date="2024-01-15",
            ),
            mock_completion,
        )
        engine._client = mock_client

        result = engine.extract("Invoice #123, Amount: $500", InvoiceSchema)

        assert result.title == "Invoice #123"
        assert result.amount == 500.00
        mock_client.messages.create_with_completion.assert_called_once()

    def test_extract_openai(self):
        """Test extraction with OpenAI provider using pre-set mock client."""
        engine = ExtractionEngine(provider="openai", model="gpt-4o")

        # Create mock client - create_with_completion returns tuple
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(prompt_tokens=80, completion_tokens=40)
        mock_client.chat.completions.create_with_completion.return_value = (
            InvoiceSchema(
                title="Invoice #456",
                amount=250.00,
            ),
            mock_completion,
        )
        engine._client = mock_client

        result = engine.extract("Invoice #456, Total: $250", InvoiceSchema)

        assert result.title == "Invoice #456"
        assert result.amount == 250.00
        mock_client.chat.completions.create_with_completion.assert_called_once()

    def test_assess_returns_assessment(self):
        """Test assessment returns Assessment object."""
        engine = ExtractionEngine(provider="anthropic")

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=200, output_tokens=30)
        mock_client.messages.create_with_completion.return_value = (
            Assessment(
                review_status=ReviewStatus.NO_REVIEW_NEEDED,
                ambiguous_fields=[],
                review_notes="",
                schema_suggestions=[],
            ),
            mock_completion,
        )
        engine._client = mock_client

        extracted = InvoiceSchema(title="Invoice #123", amount=100.00)
        result = engine.assess("Document text", InvoiceSchema, extracted)

        assert isinstance(result, Assessment)
        assert result.review_status == ReviewStatus.NO_REVIEW_NEEDED

    def test_assess_with_issues(self):
        """Test assessment that finds issues."""
        engine = ExtractionEngine(provider="anthropic")

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=200, output_tokens=50)
        mock_client.messages.create_with_completion.return_value = (
            Assessment(
                review_status=ReviewStatus.NEEDS_REVIEW,
                ambiguous_fields=["amount", "date"],
                review_notes="Amount unclear, date missing.",
                schema_suggestions=[
                    FieldSuggestion(name="currency", field_type="Optional[str]", description="Currency code"),
                ],
            ),
            mock_completion,
        )
        engine._client = mock_client

        extracted = InvoiceSchema(title="Invoice")
        result = engine.assess("Ambiguous document", InvoiceSchema, extracted)

        assert result.review_status == ReviewStatus.NEEDS_REVIEW
        assert "amount" in result.ambiguous_fields
        assert len(result.schema_suggestions) == 1

    def test_extract_prompt_contains_document(self):
        """Test that extract sends document text in prompt."""
        engine = ExtractionEngine(provider="anthropic")

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create_with_completion.return_value = (
            InvoiceSchema(title="Test"),
            mock_completion,
        )
        engine._client = mock_client

        engine.extract("This is my document content", InvoiceSchema)

        # Verify the document was included in the message
        call_args = mock_client.messages.create_with_completion.call_args
        messages = call_args.kwargs["messages"]
        assert "This is my document content" in messages[0]["content"]

    def test_assess_prompt_contains_context(self):
        """Test that assess includes document, schema, and extracted data."""
        engine = ExtractionEngine(provider="anthropic")

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=200, output_tokens=30)
        mock_client.messages.create_with_completion.return_value = (
            Assessment(
                review_status=ReviewStatus.NO_REVIEW_NEEDED,
            ),
            mock_completion,
        )
        engine._client = mock_client

        extracted = InvoiceSchema(title="My Invoice", amount=100.00)
        engine.assess("Original document text", InvoiceSchema, extracted)

        call_args = mock_client.messages.create_with_completion.call_args
        prompt = call_args.kwargs["messages"][0]["content"]

        # Verify all context is included
        assert "Original document text" in prompt
        assert "My Invoice" in prompt  # extracted data
        assert "title" in prompt  # schema field


class TestExtractionEngineErrorHandling:
    """Tests for error handling in ExtractionEngine."""

    def test_non_retryable_error_wrapped_as_api_error(self):
        """Test that non-retryable errors are wrapped in APIError."""
        engine = ExtractionEngine(provider="anthropic", max_retries=0)

        mock_client = Mock()
        mock_client.messages.create_with_completion.side_effect = Exception("Some unexpected error")
        engine._client = mock_client

        with pytest.raises(APIError) as exc_info:
            engine.extract("Document text", InvoiceSchema)

        assert "anthropic" in str(exc_info.value)

    def test_authentication_error_detected(self):
        """Test that auth errors are wrapped in AuthenticationError."""
        engine = ExtractionEngine(provider="anthropic", max_retries=0)

        mock_client = Mock()
        mock_client.messages.create_with_completion.side_effect = Exception("Invalid api_key provided")
        engine._client = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            engine.extract("Document text", InvoiceSchema)

        assert "Authentication failed" in str(exc_info.value)

    def test_assess_error_wrapped(self):
        """Test that assessment errors are wrapped appropriately."""
        engine = ExtractionEngine(provider="anthropic", max_retries=0)

        mock_client = Mock()
        mock_client.messages.create_with_completion.side_effect = Exception("Network error")
        engine._client = mock_client

        extracted = InvoiceSchema(title="Test")

        with pytest.raises(APIError) as exc_info:
            engine.assess("Document", InvoiceSchema, extracted)

        assert "Network error" in str(exc_info.value)


class TestExtractionEngineRetry:
    """Tests for retry logic in ExtractionEngine."""

    def test_retry_on_rate_limit(self):
        """Test that rate limit errors trigger retries."""
        engine = ExtractionEngine(provider="anthropic", max_retries=2, retry_delay=0.01)

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=100, output_tokens=50)
        # Fail twice with rate limit, then succeed
        mock_client.messages.create_with_completion.side_effect = [
            Exception("Rate limit exceeded"),
            Exception("429 Too Many Requests"),
            (InvoiceSchema(title="Success"), mock_completion),
        ]
        engine._client = mock_client

        result = engine.extract("Document", InvoiceSchema)

        assert result.title == "Success"
        assert mock_client.messages.create_with_completion.call_count == 3

    def test_retry_exhausted_raises_rate_limit_error(self):
        """Test that exhausted retries for rate limit raises RateLimitError."""
        engine = ExtractionEngine(provider="anthropic", max_retries=1, retry_delay=0.01)

        mock_client = Mock()
        mock_client.messages.create_with_completion.side_effect = Exception("Rate limit exceeded")
        engine._client = mock_client

        with pytest.raises(RateLimitError) as exc_info:
            engine.extract("Document", InvoiceSchema)

        assert "Rate limit exceeded" in str(exc_info.value)
        assert mock_client.messages.create_with_completion.call_count == 2  # initial + 1 retry

    def test_retry_on_server_error(self):
        """Test that 5xx errors trigger retries."""
        engine = ExtractionEngine(provider="anthropic", max_retries=1, retry_delay=0.01)

        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create_with_completion.side_effect = [
            Exception("503 Service Unavailable"),
            (InvoiceSchema(title="Recovered"), mock_completion),
        ]
        engine._client = mock_client

        result = engine.extract("Document", InvoiceSchema)

        assert result.title == "Recovered"

    def test_no_retry_on_auth_error(self):
        """Test that authentication errors don't trigger retries."""
        engine = ExtractionEngine(provider="anthropic", max_retries=3, retry_delay=0.01)

        mock_client = Mock()
        mock_client.messages.create_with_completion.side_effect = Exception("authentication failed")
        engine._client = mock_client

        with pytest.raises(AuthenticationError):
            engine.extract("Document", InvoiceSchema)

        # Should only be called once (no retries for auth errors)
        assert mock_client.messages.create_with_completion.call_count == 1

    def test_is_retryable_error(self):
        """Test the retryable error detection."""
        engine = ExtractionEngine()

        # Retryable errors
        assert engine._is_retryable_error(Exception("rate limit exceeded")) is True
        assert engine._is_retryable_error(Exception("429 Too Many Requests")) is True
        assert engine._is_retryable_error(Exception("503 Service Unavailable")) is True
        assert engine._is_retryable_error(Exception("timeout")) is True
        assert engine._is_retryable_error(Exception("overloaded")) is True

        # Non-retryable errors
        assert engine._is_retryable_error(Exception("authentication failed")) is False
        assert engine._is_retryable_error(Exception("invalid request")) is False
        assert engine._is_retryable_error(ValueError("bad input")) is False

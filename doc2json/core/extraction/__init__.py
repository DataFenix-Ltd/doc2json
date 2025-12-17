import importlib.util
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Type, Any, Optional

from pydantic import BaseModel

from doc2json.models.result import Assessment, ReviewStatus
from doc2json.models.metadata import TokenUsage
from doc2json.core.exceptions import (
    SchemaNotFoundError,
    SchemaValidationError,
    ProviderError,
    APIError,
    RateLimitError,
    AuthenticationError,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResponse:
    """Extraction result with optional token usage metadata."""
    data: BaseModel
    tokens: Optional[TokenUsage] = None


@dataclass
class AssessmentResponse:
    """Assessment result with optional token usage metadata."""
    assessment: Assessment
    tokens: Optional[TokenUsage] = None


def _extract_token_usage(completion: Any) -> Optional[TokenUsage]:
    """Extract token usage from a completion object.

    Works with Anthropic and OpenAI response formats.
    """
    if completion is None:
        return None

    usage = getattr(completion, "usage", None)
    if usage is None:
        return None

    # Anthropic format
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)

    # OpenAI format
    if input_tokens is None:
        input_tokens = getattr(usage, "prompt_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "completion_tokens", None)

    if input_tokens is not None and output_tokens is not None:
        return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    return None


def load_schema_module(schema_name: str, schemas_dir: str = "schemas"):
    """Load a schema module from a Python file.

    Args:
        schema_name: Name of the schema (without .py extension)
        schemas_dir: Directory containing schema files

    Returns:
        The loaded module

    Raises:
        SchemaNotFoundError: If schema file doesn't exist
    """
    schema_path = os.path.join(schemas_dir, f"{schema_name}.py")

    if not os.path.exists(schema_path):
        raise SchemaNotFoundError(
            f"Schema file not found: {schema_path}. "
            f"Create a schema file at schemas/{schema_name}.py with a Pydantic 'Schema' class."
        )

    # Load the module dynamically
    spec = importlib.util.spec_from_file_location(schema_name, schema_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def load_schema(schema_name: str, schemas_dir: str = "schemas") -> Type[BaseModel]:
    """Load a Pydantic schema from a Python file.

    Args:
        schema_name: Name of the schema (without .py extension)
        schemas_dir: Directory containing schema files

    Returns:
        The Schema class from the module

    Raises:
        SchemaNotFoundError: If schema file doesn't exist
        SchemaValidationError: If schema is invalid (missing Schema class, not a BaseModel)
    """
    module = load_schema_module(schema_name, schemas_dir)

    # Get the Schema class
    if not hasattr(module, "Schema"):
        raise SchemaValidationError(
            f"Schema file 'schemas/{schema_name}.py' must define a 'Schema' class. "
            f"Example:\n\n"
            f"from pydantic import BaseModel\n\n"
            f"class Schema(BaseModel):\n"
            f"    title: str\n"
        )

    schema_class = getattr(module, "Schema")

    if not issubclass(schema_class, BaseModel):
        raise SchemaValidationError(
            f"Schema class in 'schemas/{schema_name}.py' must inherit from pydantic.BaseModel. "
            f"Got: {type(schema_class).__name__}"
        )

    return schema_class


def get_schema_version(schema_name: str, schemas_dir: str = "schemas") -> str:
    """Get the version of a schema file.

    Args:
        schema_name: Name of the schema (without .py extension)
        schemas_dir: Directory containing schema files

    Returns:
        Version string, or "unknown" if not defined
    """
    module = load_schema_module(schema_name, schemas_dir)
    return getattr(module, "__version__", "unknown")


class ExtractionEngine:
    """Engine for extracting structured data from documents using LLMs."""

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0  # seconds
    DEFAULT_RETRY_MULTIPLIER = 2.0  # exponential backoff

    def __init__(
        self,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.api_version = api_version  # Required for Azure OpenAI
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = None

    def _get_client(self):
        """Lazily initialize the LLM client.

        Raises:
            ProviderError: If provider is not supported or SDK is not installed
            AuthenticationError: If API key is missing or invalid
        """
        if self._client is not None:
            return self._client

        try:
            import instructor
        except ImportError:
            raise ProviderError(
                "instructor package not installed. "
                "Run: pip install instructor"
            )

        if self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ProviderError(
                    f"anthropic package not installed. "
                    f"Run: pip install doc2json[anthropic]"
                )
            try:
                self._client = instructor.from_anthropic(
                    Anthropic(
                        base_url=self.base_url,
                        api_key=self.api_key
                    )
                )
            except Exception as e:
                if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                    raise AuthenticationError(
                        "Anthropic API key not found or invalid. "
                        "Set ANTHROPIC_API_KEY environment variable.",
                        provider="anthropic",
                        original_error=e,
                    )
                raise

        elif self.provider == "openai":
            try:
                from openai import OpenAI, AzureOpenAI
            except ImportError:
                raise ProviderError(
                    f"openai package not installed. "
                    f"Run: pip install doc2json[openai]"
                )
            try:
                # Use AzureOpenAI client when api_version is specified
                if self.api_version:
                    client = AzureOpenAI(
                        azure_endpoint=self.base_url,
                        api_key=self.api_key,
                        api_version=self.api_version,
                    )
                    logger.info(f"Using Azure OpenAI (api_version={self.api_version})")
                else:
                    client = OpenAI(
                        base_url=self.base_url,
                        api_key=self.api_key,
                    )
                self._client = instructor.from_openai(client)
            except Exception as e:
                if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                    raise AuthenticationError(
                        "OpenAI API key not found or invalid. "
                        "Set OPENAI_API_KEY environment variable.",
                        provider="openai",
                        original_error=e,
                    )
                raise

        elif self.provider == "ollama":
            # Ollama is OpenAI-compatible
            try:
                from openai import OpenAI
            except ImportError:
                raise ProviderError(
                    f"openai package not installed (required for ollama). "
                    f"Run: pip install doc2json[openai]"
                )

            # Defaults for Ollama
            base_url = self.base_url or "http://localhost:11434/v1"
            api_key = self.api_key or "ollama"  # Ollama doesn't require key but client might

            try:
                # Start with TOOLS mode (best quality), will fall back to JSON if needed
                self._client = instructor.from_openai(
                    OpenAI(
                        base_url=base_url,
                        api_key=api_key,
                    ),
                    mode=instructor.Mode.TOOLS,
                )
                self._ollama_base_url = base_url
                self._ollama_api_key = api_key
            except Exception as e:
                raise APIError(
                    f"Failed to initialize Ollama client: {e}",
                    provider="ollama",
                    original_error=e,
                )

        elif self.provider == "gemini":
            try:
                import google.generativeai as genai
            except ImportError:
                raise ProviderError(
                    f"google-generativeai package not installed. "
                    f"Run: pip install doc2json[gemini]"
                )
            try:
                self._client = instructor.from_gemini(
                    genai.GenerativeModel(model_name=self.model)
                )
            except Exception as e:
                if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                    raise AuthenticationError(
                        "Google API key not found or invalid. "
                        "Set GOOGLE_API_KEY environment variable.",
                        provider="gemini",
                        original_error=e,
                    )
                raise
        else:
            raise ProviderError(
                f"Unsupported LLM provider: '{self.provider}'. "
                f"Supported providers: anthropic, openai, gemini, ollama"
            )

        return self._client

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable (rate limit, temporary failure)."""
        error_str = str(error).lower()

        # Rate limit errors
        if any(term in error_str for term in ["rate limit", "rate_limit", "429", "too many requests"]):
            return True

        # Temporary server errors
        if any(term in error_str for term in ["500", "502", "503", "504", "overloaded", "timeout"]):
            return True

        # Ollama "does not support tools" - retryable after fallback to JSON mode
        if "does not support tools" in error_str:
            if self._fallback_to_json_mode():
                return True

        return False

    def _call_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic for transient errors.

        Args:
            func: Function to call
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result of the function call

        Raises:
            RateLimitError: If rate limit is hit and retries exhausted
            APIError: For other API errors after retries exhausted
        """
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if not self._is_retryable_error(e):
                    # Non-retryable error, raise immediately
                    self._raise_api_error(e)

                if attempt < self.max_retries:
                    logger.warning(
                        f"Retryable error (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= self.DEFAULT_RETRY_MULTIPLIER
                else:
                    # Exhausted retries
                    if "rate limit" in str(e).lower() or "429" in str(e):
                        raise RateLimitError(
                            f"Rate limit exceeded after {self.max_retries + 1} attempts. "
                            f"Try again later or reduce request frequency.",
                            provider=self.provider,
                            original_error=e,
                        )
                    raise APIError(
                        f"API call failed after {self.max_retries + 1} attempts: {e}",
                        provider=self.provider,
                        original_error=e,
                    )

    def _fallback_to_json_mode(self) -> bool:
        """Fall back to JSON mode for Ollama if tools aren't supported.

        Returns:
            True if fallback was performed, False otherwise
        """
        if self.provider != "ollama":
            return False

        if not hasattr(self, "_ollama_base_url"):
            return False

        try:
            import instructor
            from openai import OpenAI

            logger.info("Model doesn't support tools, falling back to JSON mode")
            self._client = instructor.from_openai(
                OpenAI(
                    base_url=self._ollama_base_url,
                    api_key=self._ollama_api_key,
                ),
                mode=instructor.Mode.JSON,
            )
            return True
        except Exception:
            return False

    def _raise_api_error(self, error: Exception):
        """Convert provider-specific errors to our exception types."""
        error_str = str(error).lower()

        if "api_key" in error_str or "authentication" in error_str or "401" in str(error):
            raise AuthenticationError(
                f"Authentication failed for {self.provider}. Check your API key.",
                provider=self.provider,
                original_error=error,
            )

        raise APIError(
            f"API error from {self.provider}: {error}",
            provider=self.provider,
            original_error=error,
        )

    def extract(self, text: str, schema: Type[BaseModel]) -> BaseModel:
        """Extract structured data from text using the given schema.

        Args:
            text: The document text to extract from
            schema: Pydantic model class defining the extraction schema

        Returns:
            An instance of the schema with extracted data

        Raises:
            APIError: If the API call fails
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If authentication fails
        """
        response = self.extract_with_metadata(text, schema)
        return response.data

    def extract_with_metadata(
        self, text: str, schema: Type[BaseModel]
    ) -> ExtractionResponse:
        """Extract structured data with token usage metadata.

        Args:
            text: The document text to extract from
            schema: Pydantic model class defining the extraction schema

        Returns:
            ExtractionResponse with data and optional token usage

        Raises:
            APIError: If the API call fails
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If authentication fails
        """
        client = self._get_client()

        def _do_extract():
            if self.provider == "anthropic":
                return client.messages.create_with_completion(
                    model=self.model,
                    max_tokens=4096,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Extract the following information from this document:\n\n{text}",
                        }
                    ],
                    response_model=schema,
                )
            else:  # openai, gemini, ollama
                return client.chat.completions.create_with_completion(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Extract the following information from this document:\n\n{text}",
                        }
                    ],
                    response_model=schema,
                )

        result = self._call_with_retry(_do_extract)

        # create_with_completion returns (model, completion) tuple
        if isinstance(result, tuple) and len(result) == 2:
            data, completion = result
            tokens = _extract_token_usage(completion)
            return ExtractionResponse(data=data, tokens=tokens)

        # Fallback if not a tuple (shouldn't happen)
        return ExtractionResponse(data=result, tokens=None)

    def assess(
        self,
        text: str,
        schema: Type[BaseModel],
        extracted_data: BaseModel,
    ) -> Assessment:
        """Assess the quality of an extraction result.

        Args:
            text: The original document text
            schema: The Pydantic schema used for extraction
            extracted_data: The extracted data to assess

        Returns:
            An Assessment with review status and notes

        Raises:
            APIError: If the API call fails
            RateLimitError: If rate limit is exceeded
        """
        response = self.assess_with_metadata(text, schema, extracted_data)
        return response.assessment

    def assess_with_metadata(
        self,
        text: str,
        schema: Type[BaseModel],
        extracted_data: BaseModel,
    ) -> AssessmentResponse:
        """Assess the quality of an extraction with token usage metadata.

        Args:
            text: The original document text
            schema: The Pydantic schema used for extraction
            extracted_data: The extracted data to assess

        Returns:
            AssessmentResponse with assessment and optional token usage

        Raises:
            APIError: If the API call fails
            RateLimitError: If rate limit is exceeded
        """
        client = self._get_client()

        # Build prompt with context
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        extracted_json = json.dumps(extracted_data.model_dump(mode="json"), indent=2)

        prompt = f"""Assess this extraction. Be terse.

DOCUMENT:
{text}

SCHEMA:
{schema_json}

EXTRACTED:
{extracted_json}

Return:
- review_status: "needs_review" (errors/missing data), "suggested_review" (minor issues), or "no_review_needed"
- ambiguous_fields: field names with uncertain values
- review_notes: 1-2 sentences max, only if issues exist
- schema_suggestions: list of fields worth adding, each with:
  - name: snake_case field name
  - field_type: Python type (str, int, float, bool, Optional[str], list[str], etc.)
  - description: short description for Field()
  - sample_value: example value from the document (optional)
"""

        def _do_assess():
            if self.provider == "anthropic":
                return client.messages.create_with_completion(
                    model=self.model,
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=Assessment,
                )
            else:  # openai, gemini, ollama
                return client.chat.completions.create_with_completion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=Assessment,
                )

        result = self._call_with_retry(_do_assess)

        # create_with_completion returns (model, completion) tuple
        if isinstance(result, tuple) and len(result) == 2:
            assessment, completion = result
            tokens = _extract_token_usage(completion)
            return AssessmentResponse(assessment=assessment, tokens=tokens)

        # Fallback if not a tuple
        return AssessmentResponse(assessment=result, tokens=None)

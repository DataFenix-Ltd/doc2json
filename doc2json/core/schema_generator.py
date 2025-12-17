"""Generate suggested schema updates based on extraction feedback."""

import json
from collections import Counter
from pathlib import Path
from typing import Type, Any

from pydantic import BaseModel

from doc2json.core.extraction import load_schema, ExtractionEngine


def generate_suggested_schema(
    original_schema: Type[BaseModel],
    field_suggestions: list[dict[str, Any]],
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Generate a new schema file incorporating field suggestions.

    Args:
        original_schema: The original Pydantic schema class
        field_suggestions: List of field suggestion dicts with name, field_type, description, sample_value
        provider: LLM provider name
        model: Model name

    Returns:
        Python code for the suggested schema
    """
    if not field_suggestions:
        return ""

    # Deduplicate and merge field suggestions (same field may appear multiple times)
    fields_by_name: dict[str, dict] = {}
    for suggestion in field_suggestions:
        name = suggestion["name"]
        if name not in fields_by_name:
            fields_by_name[name] = {
                "name": name,
                "field_type": suggestion.get("field_type", "Optional[str]"),
                "description": suggestion.get("description", ""),
                "sample_values": [],
            }
        if suggestion.get("sample_value"):
            fields_by_name[name]["sample_values"].append(suggestion["sample_value"])

    # Get original schema as JSON schema
    original_json = json.dumps(original_schema.model_json_schema(), indent=2)

    # Format field suggestions for the prompt
    field_lines = []
    for field in fields_by_name.values():
        samples = field["sample_values"][:3]  # Limit to 3 examples
        samples_str = f" (examples: {samples})" if samples else ""
        field_lines.append(
            f"- {field['name']}: {field['field_type']} - {field['description']}{samples_str}"
        )

    # Build prompt
    prompt = f"""Given this Pydantic schema and field suggestions from document analysis, generate an updated schema.

CURRENT SCHEMA (as JSON Schema):
{original_json}

NEW FIELDS TO ADD:
{chr(10).join(field_lines)}

Generate a complete Python file with the updated Pydantic schema.
Requirements:
- Keep the class named 'Schema'
- Add the new fields with the suggested types (prefer Optional[] for fields that may not always be present)
- Keep all existing fields unchanged
- Include Field(description="...") for all fields
- Use modern Python typing (3.11+)
- Include necessary imports (pydantic, typing)
- Add a __version__ = "1" at the top

Return only the Python code, no explanation."""

    # Use raw client (not Instructor) since we want text, not structured output
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.content[0].text
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.choices[0].message.content
    elif provider == "gemini":
        import google.generativeai as genai
        client = genai.GenerativeModel(model_name=model)
        response = client.generate_content(prompt)
        code = response.text
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # Strip markdown code blocks if present
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]

    return code.strip()

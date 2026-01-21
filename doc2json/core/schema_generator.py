"""Generate suggested schema updates based on extraction feedback."""

import json
from collections import Counter
from pathlib import Path
from typing import Type, Any

from pydantic import BaseModel

from doc2json.core.extraction import load_schema, ExtractionEngine
from doc2json.core.archetypes import ARCHETYPES, get_archetype_prompt


def generate_suggested_schema(
    original_schema: Type[BaseModel],
    field_suggestions: list[dict[str, Any]],
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    api_key: str = None,
    base_url: str = None,
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
        client = Anthropic(api_key=api_key, base_url=base_url)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.content[0].text
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.choices[0].message.content
    elif provider == "gemini":
        import google.generativeai as genai
        if api_key:
            genai.configure(api_key=api_key)
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


def design_initial_schema(
    document_type: str,
    description: str,
    sample_text: str = "",
    archetype: str = None,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    api_key: str = None,
    base_url: str = None,
) -> str:
    """Design a new Pydantic schema based on user description and optional sample.

    Args:
        document_type: Name of the document type (e.g. 'Invoice')
        description: User's description of what they want to extract
        sample_text: Optional sample text from a document
        archetype: Optional archetype name to use as a guide
        provider: LLM provider name
        model: Model name

    Returns:
        Python code for the designed schema
    """
    archetype_info = ""
    if archetype:
        archetype_info = f"\nGUIDELINE ARCHETYPE:\n{get_archetype_prompt(archetype)}\n"

    sample_info = ""
    if sample_text:
        # Truncate sample text to avoid prompt bloat
        sample_info = f"\nSAMPLE DOCUMENT TEXT (TRUNCATED):\n{sample_text[:2000]}\n"

    prompt = f"""You are an expert at designing Pydantic schemas for LLM document extraction.
Your goal is to create a schema that will be used with 'instructor' or similar libraries to get validated JSON from unstructured documents.

DOCUMENT TYPE: {document_type}
USER DESCRIPTION: {description}
{archetype_info}{sample_info}
DESIGN RULES:
1. Pydantic 2.x: The main class MUST be named 'Schema' and inherit from pydantic.BaseModel.
2. Field Descriptions: EVERY field must have a Field(description="...") with clear instructions for the LLM.
3. Simple Types: Use str, float, int, and datetime.date. Avoid complex or custom types. LLMs handle these basic types best.
4. Minimal Nesting: Prefer a flat structure. Only use nested models for clear recurring structures (e.g., list items). No more than 2 levels of nesting.
5. NO RECURSION: Do not define models that reference themselves.
6. Enums: Use Enums for fields with a small set of fixed values (e.g., currency). Limit Enums to a maximum of 15 values.
7. Modern Python: Use list[Type] and Optional[Type] (from typing) for type hints.
8. Versioning: Include __version__ = "1" at the top level of the file.

Generate a complete Python file. Return ONLY the code, no explanation or markdown blocks.
"""

    # Reuse the raw LLM call logic from generate_suggested_schema
    # (In a real refactor, we'd consolidate this)
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key, base_url=base_url)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.content[0].text
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.choices[0].message.content
    elif provider == "gemini":
        import google.generativeai as genai
        if api_key:
            genai.configure(api_key=api_key)
        client = genai.GenerativeModel(model_name=model)
        response = client.generate_content(prompt)
        code = response.text
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # Strip markdown code blocks if present
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]

    return code.strip()

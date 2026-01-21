import pytest
from unittest.mock import MagicMock, patch
from doc2json.core.schema_generator import design_initial_schema
import os

# Mock documentation for testing
SAMPLE_TEXT = """
INV-2024-001
Date: 2024-01-15
Vendor: Acme Corp
Total: $125.50
Items:
- Widget A: $50.00
- Gadget B: $75.50
"""

@pytest.fixture
def mock_llm_response():
    return """
from pydantic import BaseModel, Field
from typing import Optional
import datetime

__version__ = "1"

class InvoiceItem(BaseModel):
    description: str = Field(description="Item name")
    price: float = Field(description="Unit price")

class Schema(BaseModel):
    invoice_number: str = Field(description="The invoice ID")
    date: datetime.date = Field(description="Issue date")
    items: list[InvoiceItem] = Field(description="List of items")
    total: float = Field(description="Total amount")
"""

@patch("anthropic.Anthropic")
def test_design_initial_schema_anthropic(mock_anthropic, mock_llm_response):
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=f"```python\n{mock_llm_response}\n```")]
    mock_client.messages.create.return_value = mock_response

    # Run
    code = design_initial_schema(
        document_type="Invoice",
        description="Extract invoice details and items",
        sample_text=SAMPLE_TEXT,
        archetype="Invoice",
        provider="anthropic"
    )

    # Verify
    assert "class Schema(BaseModel):" in code
    assert "class InvoiceItem(BaseModel):" in code
    assert "__version__ = \"1\"" in code
    assert "Field(description=" in code
    assert "datetime.date" in code

def test_archetype_prompt_inclusion():
    with patch("doc2json.core.schema_generator.get_archetype_prompt") as mock_get_arch:
        mock_get_arch.return_value = "ARCHETYPE CONTEXT"
        
        # We just want to check if the prompt building logic works
        # We'll mock the LLM call to return quickly
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="code")]
            mock_client.messages.create.return_value = mock_response

            design_initial_schema(
                document_type="Invoice",
                description="desc",
                archetype="Invoice"
            )
            
            # Check inner prompt via call args if possible, or just trust the logic
            mock_get_arch.assert_called_once_with("Invoice")

def test_generated_code_validity(mock_llm_response):
    """Verify that the generated code can actually be executed and loaded."""
    # Create a temporary file
    test_schema_path = "schemas/test_generated.py"
    os.makedirs("schemas", exist_ok=True)
    
    try:
        with open(test_schema_path, "w") as f:
            f.write(mock_llm_response)
        
        # Try to load it using doc2json's loader
        from doc2json.core.extraction import load_schema
        schema_class = load_schema("test_generated")
        
        assert schema_class.__name__ == "Schema"
        assert "invoice_number" in schema_class.model_fields
        assert "items" in schema_class.model_fields
        
    finally:
        if os.path.exists(test_schema_path):
            os.remove(test_schema_path)

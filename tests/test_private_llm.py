import pytest
from unittest.mock import MagicMock, patch
import sys
import os
from doc2json.config.loader import load_config, LLMConfig
from doc2json.core.extraction import ExtractionEngine, ProviderError, AuthenticationError

MOCK_CONFIG_YAML = """
schemas:
  - example

llm:
  provider: ollama
  model: llama3
  base_url: http://localhost:11434/v1
  api_key: ollama
"""

def test_llm_config_parsing(tmp_path):
    config_file = tmp_path / "doc2json.yml"
    config_file.write_text(MOCK_CONFIG_YAML)
    
    config = load_config(str(config_file))
    
    assert config.llm.provider == "ollama"
    assert config.llm.model == "llama3"
    assert config.llm.base_url == "http://localhost:11434/v1"
    assert config.llm.api_key == "ollama"

# Fixture to mock sys.modules for openai and instructor
@pytest.fixture
def mock_modules():
    mock_openai = MagicMock()
    mock_instructor = MagicMock()
    
    with patch.dict(sys.modules, {
        "openai": mock_openai,
        "instructor": mock_instructor
    }):
        yield mock_openai, mock_instructor

def test_extraction_engine_ollama_init(mock_modules):
    mock_openai, mock_instructor = mock_modules
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    
    engine = ExtractionEngine(
        provider="ollama",
        model="llama3",
        base_url="http://custom:1234",
        api_key="secret"
    )
    
    # Act
    client = engine._get_client()
    
    # Assert
    mock_openai.OpenAI.assert_called_with(
        base_url="http://custom:1234",
        api_key="secret"
    )
    mock_instructor.from_openai.assert_called()
    call_kwargs = mock_instructor.from_openai.call_args.kwargs
    assert "mode" not in call_kwargs or call_kwargs["mode"] != "json"

def test_extraction_engine_ollama_defaults(mock_modules):
    mock_openai, mock_instructor = mock_modules
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    
    engine = ExtractionEngine(
        provider="ollama",
        model="llama3"
    )
    
    # Act
    client = engine._get_client()
    
    # Assert
    mock_openai.OpenAI.assert_called_with(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )

def test_extraction_engine_unsupported_provider():
    engine = ExtractionEngine(provider="invalid")
    with pytest.raises(ProviderError):
        engine._get_client()

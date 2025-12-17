# LLM Provider Guide

This guide helps you choose the right LLM provider for your document extraction needs, with clear guidance on **data privacy** implications.

## Data Privacy Overview

| Category | Providers | Your Data |
|----------|-----------|-----------|
| **Public Cloud** | Anthropic, OpenAI, Google, Groq, Together, Fireworks | Sent to provider's servers |
| **Enterprise Cloud** | Azure OpenAI, Amazon Bedrock, Google Vertex AI | Stays in your cloud tenant |
| **Private/Local** | Ollama | Never leaves your machine |

> **Important**: When processing sensitive documents (PII, financial data, legal documents), consider whether your data governance policies allow sending data to cloud providers. **Enterprise cloud** options keep data within your own cloud environment.

---

## Public Cloud Providers

These providers process your documents on their servers.

### Anthropic (Claude)

**Best for**: Highest accuracy, complex schemas, nuanced extraction

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
```

**Current Models** (December 2025):

| Model | API ID | Speed | Best For |
|-------|--------|-------|----------|
| Claude Opus 4.5 | `claude-opus-4-5-20251101` | Slower | Best overall, coding, agents |
| Claude Sonnet 4.5 | `claude-sonnet-4-5-20241022` | Fast | Real-world agents, coding |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251015` | Fastest | Low latency, cost-sensitive |

**Context**: 200K tokens (1M in preview for Sonnet)

**Setup**:
```bash
pip install doc2json[anthropic]
export ANTHROPIC_API_KEY=sk-ant-...
```

**Data policy**: https://www.anthropic.com/policies/privacy

Sources: [Anthropic Models Overview](https://docs.anthropic.com/en/docs/about-claude/models/overview), [Claude Opus 4.5 Announcement](https://www.anthropic.com/news/claude-opus-4-5)

---

### OpenAI (GPT)

**Best for**: Wide compatibility, strong instruction following

```yaml
llm:
  provider: openai
  model: gpt-4.1
```

**Current Models** (December 2025):

| Model | Speed | Best For |
|-------|-------|----------|
| `gpt-5.2` | Medium | Smartest, most precise |
| `gpt-4.1` | Fast | Coding, instruction following (1M context) |
| `gpt-4.1-mini` | Very fast | Cost-effective |
| `gpt-4.1-nano` | Fastest | Simple tasks |
| `o3`, `o4-mini` | Slow | Deep reasoning, multi-step problems |

**Note**: GPT-4o is now legacy; GPT-4.1 recommended for new projects.

**Setup**:
```bash
pip install doc2json[openai]
export OPENAI_API_KEY=sk-...
```

**Data policy**: https://openai.com/policies/privacy-policy

Sources: [OpenAI Models](https://platform.openai.com/docs/models), [GPT-4.1 Announcement](https://openai.com/index/gpt-4-1/)

---

### Google Gemini

**Best for**: Long context (1M tokens), multimodal, Google Cloud integration

```yaml
llm:
  provider: gemini
  model: gemini-3-pro
```

**Current Models** (December 2025):

| Model | Best For |
|-------|----------|
| `gemini-3-pro` | Agentic coding, complex reasoning |
| `gemini-2.5-pro` | General purpose |
| `gemini-2.5-flash` | Fast, cost-effective |

**Context**: 1M tokens

**Pricing**: $2/M input, $12/M output (Gemini 3 Pro preview)

**Setup**:
```bash
pip install doc2json[gemini]
export GOOGLE_API_KEY=...
```

**Data policy**: https://ai.google.dev/terms

Sources: [Gemini 3 Blog](https://blog.google/products/gemini/gemini-3/), [Gemini 3 Developer Guide](https://ai.google.dev/gemini-api/docs/gemini-3)

---

### Groq (Cloud-hosted open models)

**Best for**: Fast inference of open models without local hardware

> **Recommended for getting started** - Groq offers a generous free tier with exceptional speed. In our testing, `llama-3.3-70b-versatile` extracted 5 invoices in 5.5 seconds with high accuracy - comparable to Claude at zero cost.

```yaml
llm:
  provider: openai
  base_url: https://api.groq.com/openai/v1
  api_key: ${GROQ_API_KEY}
  model: llama-3.3-70b-versatile
```

**Available Models**:

| Model | Speed | Notes |
|-------|-------|-------|
| `llama-3.3-70b-versatile` | 280 tok/s | **Recommended** - fast, accurate, free |
| `qwen/qwen3-32b` | 400 tok/s | Good for structured output |
| `llama-3.1-8b-instant` | 560 tok/s | Fast, smaller tasks |

**Setup**:
```bash
pip install doc2json[openai]
export GROQ_API_KEY=gsk_...
```

Get a **free** API key at https://console.groq.com

**Data policy**: https://groq.com/privacy-policy/

---

### Together AI

**Best for**: Wide selection of open models, competitive pricing

```yaml
llm:
  provider: openai
  base_url: https://api.together.xyz/v1
  api_key: ${TOGETHER_API_KEY}
  model: meta-llama/Llama-3.3-70B-Instruct-Turbo
```

**Setup**:
```bash
pip install doc2json[openai]
export TOGETHER_API_KEY=...
```

---

### Fireworks AI

**Best for**: Fast inference, serverless deployment

```yaml
llm:
  provider: openai
  base_url: https://api.fireworks.ai/inference/v1
  api_key: ${FIREWORKS_API_KEY}
  model: accounts/fireworks/models/llama-v3p3-70b-instruct
```

**Setup**:
```bash
pip install doc2json[openai]
export FIREWORKS_API_KEY=...
```

---

## Enterprise Cloud Providers

These providers run models **within your own cloud tenant**. Your data stays in your cloud environment and doesn't go to the model provider directly. Often required for enterprise compliance.

### Azure OpenAI

**Best for**: Enterprise compliance, Microsoft ecosystem, data residency requirements

```yaml
llm:
  provider: openai
  base_url: https://{your-resource}.openai.azure.com
  api_key: ${AZURE_OPENAI_API_KEY}
  api_version: 2024-12-01-preview
  model: gpt-4.1  # Your deployment name
```

**Available Models**: GPT-4.1, GPT-4o, GPT-4, etc. (depends on your Azure deployment)

**Setup**:
1. Create an Azure OpenAI resource in the Azure portal
2. Deploy a model (e.g., gpt-4.1)
3. Get your endpoint URL and API key from the resource

```bash
pip install doc2json[openai]
export AZURE_OPENAI_API_KEY=...
```

**Data location**: Your Azure tenant (region you selected)

---

### Amazon Bedrock

**Best for**: AWS ecosystem, Claude/Llama in your AWS account

> **Note**: Bedrock uses a different SDK (boto3) and is not yet directly supported. Use the Anthropic provider with Bedrock's Anthropic endpoint, or request Bedrock support.

**Data location**: Your AWS account (region you selected)

---

### Google Vertex AI

**Best for**: GCP ecosystem, Gemini in your GCP project

> **Note**: Vertex AI uses GCP authentication. The `gemini` provider can be configured for Vertex AI with service account credentials.

**Data location**: Your GCP project (region you selected)

---

## Private / Local Providers

These providers run models on your own hardware. **Your data never leaves your machine.**

### Ollama (Local)

**Best for**: Maximum privacy, no API costs, air-gapped environments

```yaml
llm:
  provider: ollama
  model: llama3.3
```

**Models with Function Calling Support** (use TOOLS mode):
- `llama3.1`, `llama3.2`, `llama3.3`, `llama4`
- `qwen2.5`
- `mistral-nemo`

**Other Models** (use JSON mode automatically):
- `gemma3`, `phi3`, etc.

| Model | RAM Required | Accuracy |
|-------|--------------|----------|
| `llama3.3:70b` | 48GB+ | Excellent |
| `qwen2.5:32b` | 24GB+ | Very good |
| `llama3.3:8b` | 8GB+ | Good |
| `mistral-nemo:12b` | 12GB+ | Good |

**Setup**:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.3

# Start the server (runs on http://localhost:11434)
ollama serve
```

No API key needed. No data leaves your machine.

**Automatic fallback**: doc2json automatically falls back from TOOLS mode to JSON mode if a model doesn't support function calling.

Sources: [Ollama Structured Outputs](https://ollama.com/blog/structured-outputs), [Ollama Docs](https://docs.ollama.com/capabilities/structured-outputs)

---

## Model Selection Guide

### By Use Case

| Use Case | Recommended | Why |
|----------|-------------|-----|
| **Getting started** | Groq `llama-3.3-70b` | Fast, accurate, free |
| **Highest accuracy** | Claude Sonnet 4.5 | Best at complex extraction |
| **Sensitive/private data** | Ollama `llama3.3:70b` | Data stays local |
| **Air-gapped network** | Ollama | No internet required |
| **Complex nested schemas** | Claude or GPT-4.1 | Better at structure |
| **Simple extraction** | Groq `llama-3.1-8b-instant` | Fast and free |
| **Long documents** | Gemini 3 Pro | 1M token context |

### Minimum Model Sizes for Structured Output

For reliable JSON extraction with Pydantic schemas:

| Schema Complexity | Minimum Size | Examples |
|-------------------|--------------|----------|
| Simple (5-10 fields) | 8B+ | `llama3.3:8b`, `gpt-4.1-nano` |
| Medium (10-20 fields) | 32B+ | `qwen2.5:32b`, `gpt-4.1-mini` |
| Complex (nested, lists) | 70B+ | `llama3.3:70b`, `gpt-4.1`, Claude |

Models under 8B parameters may return empty or incomplete JSON.

---

## Environment Variables

All API keys can be set in your `.env` file:

```bash
# Cloud providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
GROQ_API_KEY=gsk_...
TOGETHER_API_KEY=...
FIREWORKS_API_KEY=...

# Database passwords
SNOWFLAKE_PASSWORD=...
MONGODB_PASSWORD=...
```

doc2json loads `.env` automatically via python-dotenv.

---

## Troubleshooting

### "Model does not support tools"

Some models don't support function calling. For Ollama, doc2json automatically falls back to JSON mode. For other providers, try a different model.

### Empty or incomplete JSON output

The model is likely too small. Try a larger model (32B+ for medium complexity schemas, 70B+ for complex).

### Rate limit errors

Cloud providers have rate limits. The client handles retries automatically, but for high volume:
- Use Ollama for unlimited local inference
- Upgrade your API tier
- Add delays between requests

### Slow extraction

- **Cloud**: Try Groq (very fast) or a smaller model
- **Local**: Use a smaller model, add GPU, or increase RAM

# doc2json

> **Beta** - Actively developed and used in production, but APIs may change. [Feedback welcome!](https://github.com/DataFenix-Ltd/doc2json/issues)

**Your documents are unique. Your extraction tool should be too.**

Every industry has documents that generic AI tools don't understand. Legal contracts with jurisdiction-specific clauses. Medical intake forms with diagnosis codes. Invoices with VAT breakdowns. Shipping manifests with customs classifications.

You know the structure of your documents. doc2json lets you encode that knowledge into Pydantic schemas - then extracts exactly what you need, validated and typed.

And because your documents often contain sensitive data, you choose where the AI runs: locally on your laptop, in your enterprise cloud, or via public APIs.

## The Problem

You've probably tried this before:

**"Just use an LLM"** - You write a prompt, get back JSON... sometimes. No validation. Hallucinated fields. Different structure every time. You spend more time parsing the output than you saved.

**"Use a document extraction API"** - Generic fields that don't match your domain. "Amount" when you need "VAT-exclusive subtotal". No way to capture your industry's specific terminology.

**"Build it with LangChain"** - Three weeks later you have a fragile pipeline that breaks when documents vary. No schema versioning. No quality feedback. No idea which extractions need review.

**"Send everything to the cloud"** - Your compliance team wants to know why patient records are going to OpenAI's servers.

## The Solution

doc2json is a Python CLI that turns unstructured documents into validated JSON using LLMs and Pydantic schemas.

```
Documents (PDF, Word, HTML, text)
        ↓
   Your Pydantic Schema (you define the fields)
        ↓
   LLM Extraction (provider of your choice)
        ↓
   Validated JSON (type-checked, structured)
        ↓
   Your Destination (files, databases, warehouses)
```

**You define the schema. You choose the AI. You control your data.**

## Industry Examples

**Legal** - Extract party names, obligations, termination clauses, governing law from contracts. Run locally with Ollama for client confidentiality.

**Medical** - Parse patient intake forms into structured records: demographics, symptoms, medications, allergies. Keep PHI off public clouds.

**Finance** - Pull line items, tax breakdowns, payment terms from invoices. Load directly to Snowflake for reconciliation.

**Supply Chain** - Extract shipment details, HS codes, weights, origins from customs documents. Connect to your existing data warehouse.

**Insurance** - Parse claims forms, policy documents, coverage details. Maintain audit trails with schema versioning.

**Real Estate** - Extract property details, terms, contingencies from purchase agreements and leases.

## Quick Start

### 1. Install

```bash
pip install doc2json[openai]  # or [anthropic], [gemini], [all]
```

### 2. Initialize

```bash
doc2json init
```

This creates your project structure:
```
doc2json.yml       # Configuration
schemas/           # Your Pydantic schemas
sources/           # Input documents
outputs/           # Extracted JSON
```

### 3. Define Your Schema

You can let the AI design an initial schema for you:

```bash
doc2json define my_document --sample sources/example/sample.pdf
```

This will guide you through:
1.  **Archetype choice**: (Invoice, Contract, etc.)
2.  **Naming & Context**: (e.g., "UK Property Law")
3.  **Preview**: See the generated Pydantic code before saving.

Or, you can manually edit `schemas/example.py`. The field descriptions guide the LLM. Nested models just work.

### 4. Extract Your Data

```bash
# Put your documents in sources/example/
doc2json extract
```

Output appears in `outputs/example.jsonl` - validated, structured, ready to use.

## Schema Evolution

Here's what makes doc2json different: **the AI helps you improve your schema**.

Enable assessment in your config:

```yaml
schemas:
  - name: invoice
    assess: true
```

Now when you run extractions, the LLM evaluates each result and suggests missing fields it noticed in your documents:

```bash
doc2json extract --assess
# "Noticed 'payment_terms' in 8/10 documents - consider adding to schema"
# "Noticed 'purchase_order_number' in 6/10 documents - consider adding to schema"

doc2json improve
# Generates updated schema (schemas/invoice_suggested.py)

doc2json apply
# Backs up old schema (invoice_v1.py), promotes new version
```

Your schema evolves based on real data, not guesswork. Every extraction records which schema version was used for full traceability.

## Privacy Tiers

Your documents, your choice:

| Tier | Provider | Your Data |
|------|----------|-----------|
| **Local** | Ollama | Never leaves your machine |
| **Enterprise** | Azure OpenAI | Stays in your cloud tenant |
| **Public Cloud** | Anthropic, OpenAI, Gemini, Groq | Sent to provider's servers |

### Run Locally with Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.3
```

```yaml
# doc2json.yml
llm:
  provider: ollama
  model: llama3.3
```

No API keys. No data leaving your machine. No per-token costs.

### Enterprise Cloud (Azure OpenAI)

```yaml
llm:
  provider: openai
  base_url: https://your-resource.openai.azure.com
  api_key: ${AZURE_OPENAI_API_KEY}
  api_version: 2024-12-01-preview
  model: gpt-4.1
```

Data stays in your Azure tenant. Required for many compliance frameworks.

### Public Cloud (Fastest, Most Accurate)

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
```

Best accuracy for complex extractions. See [docs/models.md](docs/models.md) for model recommendations.

## Production Connectors

doc2json isn't just for prototypes. Connect to real data infrastructure:

**Sources**: Local files, AWS S3, Google Drive, Azure Blob Storage

**Destinations**: JSONL files, PostgreSQL, MongoDB, Snowflake, BigQuery, SQLite, MySQL

```yaml
# Example: S3 → Snowflake pipeline
source:
  type: s3
  bucket: legal-documents
  prefix: contracts/2024/

destination:
  type: snowflake
  account: xy12345.us-east-1
  user: ${SNOWFLAKE_USER}
  password: ${SNOWFLAKE_PASSWORD}
  database: ANALYTICS
  schema: RAW
  warehouse: COMPUTE_WH
```

See [docs/reference.md](docs/reference.md) for all connector options.

## Commands

| Command | What it does |
|---------|--------------|
| `doc2json init` | Create project structure & configure provider |
| `doc2json define` | LLM-powered interactive schema design |
| `doc2json extract` | Extract validated data from documents |
| `doc2json extract --dry-run` | Preview without calling the LLM |
| `doc2json validate` | Check configuration and schema consistency |
| `doc2json preview` | Show the JSON schema sent to the LLM |
| `doc2json improve` | Generate schema updates from feedback |
| `doc2json apply` | Apply suggested schema (with versioning) |

## Why doc2json?

**Schema-first** - Pydantic models with type hints and validation. No more hoping the JSON looks right.

**Domain-specific** - Your schema encodes your domain knowledge. Extract exactly what matters to your business.

**Privacy-conscious** - Run locally, in your enterprise cloud, or via public APIs. You decide.

**Self-improving** - The assessment loop discovers fields you missed. Your schema evolves with your data.

**Production-ready** - Real connectors to real infrastructure. Metadata tracking. Schema versioning.

**Open source** - MIT licensed. No vendor lock-in. See exactly what it does.

## Installation Options

```bash
# Core + LLM provider
pip install doc2json[anthropic]    # Claude
pip install doc2json[openai]       # OpenAI, Azure, Groq, Together, Ollama
pip install doc2json[gemini]       # Google Gemini
pip install doc2json[all]          # All providers

# Add connectors as needed
pip install doc2json[s3]           # AWS S3 source
pip install doc2json[snowflake]    # Snowflake destination
pip install doc2json[postgres]     # PostgreSQL destination
pip install doc2json[sql]          # Generic SQL (MySQL, SQLite, etc.)
```

## Documentation

- **[Reference Guide](docs/reference.md)** - Full configuration options, all connectors, file format support
- **[Model Selection](docs/models.md)** - Choosing the right LLM provider for your use case

## License

MIT - Use it however you want.

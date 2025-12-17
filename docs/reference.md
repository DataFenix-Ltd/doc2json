# Reference Guide

Complete configuration reference for doc2json. For an introduction, see the [main README](../README.md).

## Installation

```bash
pip install doc2json[anthropic]  # For Anthropic Claude
# or
pip install doc2json[openai]     # For OpenAI
# or
pip install doc2json[gemini]     # For Google Gemini
# or
pip install doc2json[all]        # All providers
pip install doc2json[sql]        # Generic SQL (PostgreSQL, MySQL, SQLite, etc.)
pip install doc2json[s3,snowflake] # Specific connectors
```

## Quick Start

### 1. Set up your API key

```bash
cp .env.example .env
# Edit .env with your API key
source .env
```

### 2. Initialize a project

```bash
doc2json init
```

This creates:
```
doc2json.yml    # Configuration
schemas/           # Pydantic schema definitions
sources/           # Input documents
outputs/           # Extracted JSON
```

### 3. Define your schema

Edit `schemas/example.py` with your Pydantic model:

```python
__version__ = "1"

from pydantic import BaseModel, Field
from typing import Optional

class Schema(BaseModel):
    """Your document schema."""
    title: str = Field(description="Document title")
    date: Optional[str] = Field(default=None, description="Document date")
    # Add your fields...
```

### 4. Add documents

Put your documents in `sources/`. Supported formats:
- Plain text (`.txt`, `.md`)
- PDF (`.pdf`) - requires `pip install doc2json[pdf]`
- Word (`.docx`) - requires `pip install doc2json[docx]`
- HTML (`.html`, `.htm`) - requires `pip install doc2json[html]`

### 5. Run extraction

```bash
doc2json run
```

Output is written to `outputs/example.jsonl`.

## Configuration

Edit `doc2json.yml`:

```yaml
# Define schemas to extract (by convention: schemas/<name>.py, sources/<name>/)
schemas:
  - name: invoice
    assess: true           # Enable quality assessment

# Source configuration (optional - defaults to local sources/<schema>/)
source:
  type: s3
  bucket: my-documents-bucket
  prefix: invoices/2024/

# Destination configuration (optional - defaults to JSONL)
destination:
  type: snowflake
  account: xy12345.us-east-2
  user: myuser
  password: mypassword
  database: ANALYTICS
  schema: RAW
  warehouse: COMPUTE_WH

llm:
  provider: anthropic      # anthropic, openai, or gemini
  model: claude-sonnet-4-20250514
```

You can also use the simpler format for schemas:

```yaml
schemas:
  - invoice              # Just the name, assess defaults to false
```

## Commands

| Command | Description |
|---------|-------------|
| `doc2json init` | Initialize a new project |
| `doc2json run` | Extract data from documents |
| `doc2json preview` | Preview the current schema |
| `doc2json test` | Validate configuration |
| `doc2json suggest-schema` | Generate schema improvements from feedback |
| `doc2json accept-suggestion` | Apply suggested schema changes |

## Schema Assessment

When `assess: true` is set, each extraction is evaluated for quality:

- **needs_review** - Significant issues found
- **suggested_review** - Minor ambiguities
- **no_review_needed** - Extraction looks good

Assessment results include:
- Ambiguous fields that may need checking
- Review notes explaining issues
- Schema suggestions for improvements

## Schema Versioning

Schemas are versioned automatically:

1. Run extractions with `assess: true`
2. Run `doc2json suggest-schema` to generate improvements
3. Review the suggested schema
4. Run `doc2json accept-suggestion` to apply

This backs up the current schema (e.g., `example_v1.py`) and promotes the new version.

Each JSONL record includes `_schema` and `_schema_version` for traceability.

## Supported Providers

| Provider | Install | Data Privacy | Notes |
|----------|---------|--------------|-------|
| Anthropic | `[anthropic]` | Cloud | Best accuracy |
| OpenAI | `[openai]` | Cloud | Wide compatibility |
| Gemini | `[gemini]` | Cloud | 1M token context |
| Groq/Together/Fireworks | `[openai]` | Cloud | Fast open models |
| **Ollama** | `[openai]` | **Local** | Data never leaves your machine |

> **Privacy Note**: Cloud providers send your documents to their servers. For sensitive data, use Ollama to keep everything local.

See **[docs/models.md](docs/models.md)** for detailed model selection guidance, pricing, and configuration examples.

doc2json uses [Instructor](https://github.com/jxnl/instructor) for structured LLM output.

## Connectors

Configure sources and destinations in `doc2json.yml`. Ensure you install the required extras (e.g., `pip install doc2json[s3]`).

### Sources

**1. Local File System** (`type: local`)
Default source - no configuration needed if you follow the convention (`sources/<schema>/`).
```yaml
source:
  type: local
  path: sources/custom-path/
```

**2. AWS S3** (`type: s3`)
Requires `pip install doc2json[s3]`.
```yaml
source:
  type: s3
  bucket: my-bucket
  prefix: path/to/files/  # Optional
  # Optional credentials (defaults to env vars/AWS profile)
  aws_access_key_id: ...
  aws_secret_access_key: ...
  region_name: us-east-1
```

**3. Google Drive** (`type: google_drive`)
Requires `pip install doc2json[google-drive]`.
```yaml
source:
  type: google_drive
  folder_id: 1A2B3C...   # Folder ID from URL
  credentials_file: credentials.json  # Service account JSON
  recursive: true
```

**4. Azure Blob Storage** (`type: azure_blob`)
Requires `pip install doc2json[azure-blob]`.
```yaml
source:
  type: azure_blob
  connection_string: "DefaultEndpointsProtocol=https;..."
  container_name: my-container
  prefix: invoices/
```

### Destinations

**1. JSONL Files** (`type: jsonl`)
Default destination - outputs to `outputs/<schema>.jsonl` by convention.
```yaml
destination:
  type: jsonl
  path: outputs/custom-output.jsonl  # Optional
```

**2. PostgreSQL** (`type: postgres`)
Requires `pip install doc2json[postgres]`.
```yaml
destination:
  type: postgres
  host: localhost
  port: 5432
  database: my_db
  user: postgres
  password: password
  table: extractions              # Optional, default: extractions
  metadata_table: extraction_meta # Optional, default: extraction_metadata
```

**3. MongoDB** (`type: mongodb`)
Requires `pip install doc2json[mongodb]`.
```yaml
destination:
  type: mongodb
  connection_string: mongodb://localhost:27017
  database: my_db
  collection: extractions
```

**4. Snowflake** (`type: snowflake`)
Requires `pip install doc2json[snowflake]`.

Option A - Browser SSO (recommended for interactive use):
```yaml
destination:
  type: snowflake
  account: xy12345.us-east-1
  user: username
  authenticator: externalbrowser  # Opens browser for SSO login
  warehouse: COMPUTE_WH
  database: ANALYTICS
  schema: RAW
```

Option B - Password (supports environment variables):
```yaml
destination:
  type: snowflake
  account: xy12345.us-east-1
  user: username
  password: ${SNOWFLAKE_PASSWORD}  # Reads from env var
  warehouse: COMPUTE_WH
  database: ANALYTICS
  schema: RAW
  role: MY_ROLE                    # Optional
```

**5. BigQuery** (`type: bigquery`)
Requires `pip install doc2json[bigquery]`.

Authentication: Either use `gcloud auth application-default login` or provide a service account file.
```yaml
destination:
  type: bigquery
  project_id: my-gcp-project
  dataset_id: my_dataset
  location: US                    # Optional, default: US
  credentials_file: service-account.json  # Optional if using gcloud auth
```

**6. SQL (Generic via SQLAlchemy)** (`type: sql`)
Requires `pip install doc2json[sql]`. Supports PostgreSQL, MySQL, SQLite, SQL Server, and any SQLAlchemy-compatible database.

```yaml
# PostgreSQL
destination:
  type: sql
  connection_string: postgresql://user:pass@localhost/mydb

# MySQL
destination:
  type: sql
  connection_string: mysql+pymysql://user:pass@localhost/mydb

# SQLite (good for local testing)
destination:
  type: sql
  connection_string: sqlite:///outputs/extractions.db

# SQL Server
destination:
  type: sql
  connection_string: mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server
```

## PDF Support

Install PDF support:

```bash
pip install doc2json[pdf]
```

This enables:
- **Text-based PDFs**: Direct text extraction using pdfplumber
- **Scanned PDFs**: Automatic OCR fallback using Tesseract

For OCR support (scanned documents), you also need Tesseract installed:

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr

# Windows
# Download from https://github.com/UB-Mannheim/tesseract/wiki
```

The PDF parser automatically detects whether a page is text-based or scanned and uses OCR only when needed.

## Word Document Support

Install Word document support:

```bash
pip install doc2json[docx]
```

This extracts text from:
- Paragraphs
- Tables (converted to pipe-separated text)

## HTML Support

Install HTML support:

```bash
pip install doc2json[html]
```

This extracts clean text from HTML files by:
- Removing scripts, styles, navigation, and other non-content elements
- Preserving meaningful text from paragraphs, headings, lists, and tables
- Automatically detecting file encoding (UTF-8, UTF-16, etc.)

Options:
- `preserve_links`: Include link URLs in the extracted text
- `preserve_images`: Include image alt text as `[Image: description]`

The HTML parser is designed to support a future web scraping module - the underlying `HTMLExtractor` class can process raw HTML strings directly.

## License

MIT

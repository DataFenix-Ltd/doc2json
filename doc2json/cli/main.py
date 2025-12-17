import click
import os
import logging
from dotenv import load_dotenv
from doc2json.config.loader import load_config, DEFAULT_CONFIG

# Load .env file automatically
load_dotenv()
from doc2json.core.utils.fs import ensure_directory, create_file_if_missing
from doc2json.core.engine import SchemaTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Example schema template created by init
DEFAULT_SCHEMA_TEMPLATE = '''"""Example schema for doc2json.

Modify this file to match your document structure.
The Schema class defines what fields to extract from your documents.
"""

__version__ = "1"

from pydantic import BaseModel, Field
from typing import Optional


class Schema(BaseModel):
    """Document extraction schema.

    Each field should have a description to guide the LLM extraction.
    """

    title: str = Field(description="Document title or subject")
    date: Optional[str] = Field(default=None, description="Date mentioned in document")
    summary: Optional[str] = Field(default=None, description="Brief summary of the document content")

    # Add your custom fields here, for example:
    # amount: Optional[float] = Field(default=None, description="Monetary amount if present")
    # author: Optional[str] = Field(default=None, description="Author or sender name")
'''

@click.group()
@click.version_option(version="0.1.0", prog_name="doc2json")
def cli():
    """doc2json: Turn unstructured documents into clean JSON."""
    pass

@cli.command()
def init():
    """Initialize a new doc2json project."""
    click.echo("Initializing doc2json project...")

    # Create directories
    ensure_directory("sources")
    ensure_directory("sources/example")  # Create example sources directory
    ensure_directory("outputs")
    ensure_directory("schemas")

    # Create config file
    if create_file_if_missing("doc2json.yml", DEFAULT_CONFIG):
        click.echo("Created doc2json.yml")
    else:
        click.echo("doc2json.yml already exists.")

    # Create example schema
    if create_file_if_missing("schemas/example.py", DEFAULT_SCHEMA_TEMPLATE):
        click.echo("Created schemas/example.py")
    else:
        click.echo("schemas/example.py already exists.")

    click.echo("\nProject initialized successfully!")
    click.echo("\nNext steps:")
    click.echo("  1. Set your API key:  export ANTHROPIC_API_KEY=sk-ant-...")
    click.echo("  2. Add documents to:  sources/example/")
    click.echo("  3. Edit your schema:  schemas/example.py")
    click.echo("  4. Run extraction:    doc2json run")

@cli.command()
@click.option("--schema", "-s", help="Run only this schema (default: all)")
@click.option("--dry-run", is_flag=True, help="Analyze schemas and documents without calling LLM")
def run(schema, dry_run):
    """Run the extraction pipeline."""
    try:
        config = load_config()
        engine = SchemaTool(config)
        if dry_run:
            engine.dry_run(schema_name=schema)
        else:
            engine.run(schema_name=schema)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.option("--schema", "-s", help="Preview only this schema (default: all)")
def preview(schema):
    """Preview configured schemas."""
    try:
        config = load_config()
        engine = SchemaTool(config)
        engine.preview(schema_name=schema)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.option("--schema", "-s", help="Test only this schema (default: all)")
def test(schema):
    """Test project consistency."""
    try:
        config = load_config()
        engine = SchemaTool(config)
        engine.test(schema_name=schema)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


def _get_schema_config(config, schema_name: str = None):
    """Get schema config, prompting user if needed."""
    if schema_name:
        schema_config = config.get_schema(schema_name)
        if not schema_config:
            available = [s.name for s in config.schemas]
            raise click.ClickException(
                f"Schema '{schema_name}' not found. Available: {', '.join(available)}"
            )
        return schema_config

    # If only one schema, use it
    if len(config.schemas) == 1:
        return config.schemas[0]

    # Multiple schemas - list them
    click.echo("Multiple schemas configured:")
    for i, s in enumerate(config.schemas, 1):
        click.echo(f"  {i}. {s.name}")
    click.echo("\nSpecify which schema to use with --schema <name>")
    raise click.ClickException("Schema name required when multiple schemas are configured")


@cli.command("suggest-schema")
@click.option("--schema", "-s", help="Schema to generate suggestions for")
@click.option("--min-percent", default=20, help="Minimum percentage of docs a field must appear in (default: 20%)")
@click.option("--min-count", default=1, help="Minimum absolute count (default: 1)")
def suggest_schema(schema, min_percent: int, min_count: int):
    """Generate updated schema based on extraction feedback."""
    import json
    from pathlib import Path
    from doc2json.core.extraction import load_schema
    from doc2json.core.schema_generator import generate_suggested_schema

    try:
        config = load_config()
        schema_config = _get_schema_config(config, schema)
        llm_config = config.llm

        # Load suggestions from sidecar file
        suggestions_path = Path(f"outputs/{schema_config.name}_suggestions.json")
        if not suggestions_path.exists():
            click.echo(f"No suggestions file found at {suggestions_path}.", err=True)
            click.echo(f"Run 'doc2json run --schema {schema_config.name}' with 'assess: true' first.", err=True)
            return

        with open(suggestions_path) as f:
            suggestions_data = json.load(f)

        field_summary = suggestions_data.get("field_summary", {})
        if not field_summary:
            click.echo("No schema suggestions found.")
            click.echo("Make sure 'assess: true' is set in config and you've run extractions.")
            return

        docs_assessed = suggestions_data.get("documents_assessed", 0)
        total_docs = suggestions_data.get("total_documents", 0)

        click.echo(f"\n--- Suggestions for '{schema_config.name}' ---")
        click.echo(f"Documents: {total_docs} total, {docs_assessed} assessed\n")

        # Show all suggestions with stats
        filtered_fields = []
        for field_name, stats in sorted(field_summary.items(), key=lambda x: -x[1]["count"]):
            count = stats["count"]
            pct = stats["percentage"]
            status = ""
            if pct >= min_percent and count >= min_count:
                status = " [INCLUDE]"
                filtered_fields.append(field_name)
            click.echo(f"  {field_name}: {count}/{docs_assessed} ({pct:.0f}%){status}")

        if not filtered_fields:
            click.echo(f"\nNo fields meet threshold ({min_percent}% and {min_count}+ occurrences).")
            click.echo("Try lowering --min-percent or --min-count")
            return

        click.echo(f"\n{len(filtered_fields)} field(s) meet threshold, generating schema...")

        # Collect field details for included fields
        field_details = []
        for doc in suggestions_data.get("documents", []):
            for suggestion in doc.get("suggestions", []):
                if suggestion["name"] in filtered_fields:
                    field_details.append(suggestion)

        # Load original schema
        schema_class = load_schema(schema_config.name)

        # Generate new schema
        new_schema_code = generate_suggested_schema(
            original_schema=schema_class,
            field_suggestions=field_details,
            provider=llm_config.provider,
            model=llm_config.model,
        )

        if not new_schema_code:
            click.echo("Failed to generate schema.")
            return

        # Write to new file
        suggested_path = f"schemas/{schema_config.name}_suggested.py"
        with open(suggested_path, "w") as f:
            f.write(new_schema_code)

        click.echo(f"\nWrote suggested schema to: {suggested_path}")

        # Show diff-like preview
        click.echo("\n--- Suggested changes ---")
        click.echo(new_schema_code[:1500] + ("..." if len(new_schema_code) > 1500 else ""))
        click.echo("-------------------------\n")

        # Prompt to accept
        if click.confirm("Accept this suggested schema?"):
            _accept_schema_suggestion(config, schema_config.name)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


def _accept_schema_suggestion(config, schema_name: str):
    """Core logic for accepting a schema suggestion."""
    from pathlib import Path
    import shutil
    import re
    from doc2json.core.extraction import get_schema_version

    current_path = Path(f"schemas/{schema_name}.py")
    suggested_path = Path(f"schemas/{schema_name}_suggested.py")

    if not suggested_path.exists():
        click.echo(f"No suggested schema found at {suggested_path}")
        click.echo(f"Run 'doc2json suggest-schema --schema {schema_name}' first.")
        return False

    if not current_path.exists():
        click.echo(f"Current schema not found at {current_path}")
        return False

    # Get current version
    current_version = get_schema_version(schema_name)
    try:
        version_num = int(current_version)
    except ValueError:
        version_num = 0

    # Backup current schema with version
    backup_path = Path(f"schemas/{schema_name}_v{current_version}.py")
    shutil.copy(current_path, backup_path)
    click.echo(f"Backed up current schema to: {backup_path}")

    # Read suggested schema and update version
    new_version = str(version_num + 1)
    suggested_code = suggested_path.read_text()

    # Update or add __version__ in suggested code
    if "__version__" in suggested_code:
        suggested_code = re.sub(
            r'__version__\s*=\s*["\'][^"\']*["\']',
            f'__version__ = "{new_version}"',
            suggested_code
        )
    else:
        # Add after docstring or at top
        if suggested_code.startswith('"""'):
            # Find end of docstring
            end = suggested_code.find('"""', 3) + 3
            suggested_code = (
                suggested_code[:end] +
                f'\n\n__version__ = "{new_version}"' +
                suggested_code[end:]
            )
        else:
            suggested_code = f'__version__ = "{new_version}"\n\n' + suggested_code

    # Write new schema
    current_path.write_text(suggested_code)
    click.echo(f"Updated {current_path} to version {new_version}")

    # Remove suggested file
    suggested_path.unlink()
    click.echo(f"Removed {suggested_path}")

    click.echo(f"\nSchema updated successfully!")
    click.echo(f"  Previous: v{current_version} (backed up)")
    click.echo(f"  Current:  v{new_version}")
    return True


@cli.command("accept-suggestion")
@click.option("--schema", "-s", help="Schema to accept suggestion for")
def accept_suggestion(schema):
    """Accept a suggested schema, versioning the current one."""
    try:
        config = load_config()
        schema_config = _get_schema_config(config, schema)
        _accept_schema_suggestion(config, schema_config.name)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file path (default: <input>.layout.json)")
@click.option("--no-vlm", is_flag=True, help="Disable VLM style extraction (enabled by default for images)")
@click.option("--vlm-model", default="gemini-3-pro-preview", help="VLM model to use (default: gemini-3-pro-preview)")
@click.option("--debug", "-d", type=click.Path(), help="Save debug images to this directory")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress")
def layout(path, output, no_vlm, vlm_model, debug, verbose):
    """Extract layout from a document.

    Detects document structure (titles, paragraphs, tables, images) and
    outputs bounding boxes with style information.

    For images/scans, VLM is used automatically for style extraction
    (requires GOOGLE_API_KEY in .env file).

    Examples:

        doc2json layout invoice.pdf

        doc2json layout scan.png

        doc2json layout scan.png --no-vlm  # Skip VLM style extraction

        doc2json layout report.pdf -o layout.json -v
    """
    import json
    from pathlib import Path as PathLib

    # Set logging level based on verbose flag
    if verbose:
        logging.getLogger("doc2json.layout").setLevel(logging.DEBUG)
        logging.getLogger("doc2json.layout").addHandler(logging.StreamHandler())

    try:
        # Lazy import to avoid loading heavy dependencies unless needed
        from doc2json.layout import LayoutExtractor, GeminiVLMClient

        input_path = PathLib(path)

        # Determine output path
        if output:
            output_path = PathLib(output)
        else:
            output_path = input_path.with_suffix(input_path.suffix + ".layout.json")

        click.echo(f"Extracting layout from: {input_path}")

        # Check if this is an image file (needs VLM for style extraction)
        image_extensions = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
        is_image = input_path.suffix.lower() in image_extensions

        # Initialize VLM client for images (unless disabled)
        vlm_client = None
        if is_image and not no_vlm:
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if api_key:
                click.echo(f"Using VLM for style extraction ({vlm_model})")
                vlm_client = GeminiVLMClient(api_key=api_key, model_name=vlm_model)
            else:
                click.echo("Note: Set GOOGLE_API_KEY in .env for style extraction from images")

        # Run extraction
        click.echo("Loading models...")
        extractor = LayoutExtractor()
        result = extractor.process(str(input_path), vlm_client=vlm_client, debug_dir=debug)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

        # Summary
        page_count = result.get("metadata", {}).get("page_count", 0)
        element_count = sum(len(p.get("elements", [])) for p in result.get("pages", []))
        origin_type = result.get("metadata", {}).get("origin_type", "unknown")

        # Count elements with text
        text_count = sum(
            1 for p in result.get("pages", [])
            for el in p.get("elements", [])
            if el.get("text_content")
        )

        click.echo(f"\nLayout extraction complete:")
        click.echo(f"  Type: {origin_type}")
        click.echo(f"  Pages: {page_count}")
        click.echo(f"  Elements: {element_count}")
        click.echo(f"  With text: {text_count}")
        click.echo(f"  Output: {output_path}")

    except ImportError as e:
        raise click.ClickException(
            f"Layout extraction requires additional dependencies.\n"
            f"Install with: pip install doc2json[layout]\n\n"
            f"Details: {e}"
        )
    except Exception as e:
        raise click.ClickException(str(e))


if __name__ == "__main__":
    cli()

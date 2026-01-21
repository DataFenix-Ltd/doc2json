import click
import os
import logging
import json
from pathlib import Path
from dotenv import load_dotenv
from doc2json.config.loader import load_config, DEFAULT_CONFIG

# Load .env file automatically
load_dotenv()
from doc2json.core.utils.fs import ensure_directory, create_file_if_missing
from doc2json.core.engine import SchemaTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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
    click.echo("\n--- doc2json Project Initialization ---")

    # Create directories
    ensure_directory("sources")
    ensure_directory("sources/example")
    ensure_directory("outputs")
    ensure_directory("schemas")

    # Interactive configuration
    provider = click.prompt("\nSelect default LLM provider", type=click.Choice(["anthropic", "openai", "gemini", "ollama"]), default="openai")
    api_key = ""
    if provider != "ollama":
        api_key = click.prompt(f"Enter your {provider.upper()}_API_KEY (optional, press Enter to skip)", default="", show_default=False)

    config_content = DEFAULT_CONFIG
    if provider != "openai" or api_key:
        # Simple string replacement for default config
        config_content = config_content.replace("provider: openai", f"provider: {provider}")
        if api_key:
            # This is a bit hacky but works for the default template
            config_content = config_content.replace("${GROQ_API_KEY}", api_key) if provider == "openai" else config_content.replace("api_key: ${GROQ_API_KEY}", f"api_key: {api_key}")

    # Create config file
    if create_file_if_missing("doc2json.yml", config_content):
        click.echo("Created doc2json.yml")
    else:
        click.echo("doc2json.yml already exists.")

    # Create example schema
    if create_file_if_missing("schemas/example.py", DEFAULT_SCHEMA_TEMPLATE):
        click.echo("Created schemas/example.py")
    else:
        click.echo("schemas/example.py already exists.")

    click.echo("\n✨ Project initialized successfully!")
    click.echo("\nNext steps:")
    if not api_key and provider != "ollama":
        click.echo(f"  1. Set your API key in doc2json.yml or export {provider.upper()}_API_KEY")
    else:
        click.echo("  1. Check your configuration in doc2json.yml")
    click.echo("  2. Define a new schema:   doc2json define <name>")
    click.echo("  3. Add documents to:      sources/<name>/")
    click.echo("  4. Start extraction:      doc2json extract")

@cli.command()
@click.option("--schema", "-s", help="Run only this schema (default: all)")
@click.option("--dry-run", is_flag=True, help="Analyze schemas and documents without calling LLM")
def extract(schema, dry_run):
    """Run the extraction pipeline."""
    try:
        config = load_config()
        engine = SchemaTool(config)
        if dry_run:
            engine.dry_run(schema_name=schema)
            click.echo("\n✨ Dry-run complete. No documents were extracted.")
            click.echo("Run without --dry-run to start real extraction.")
        else:
            engine.run(schema_name=schema)
            # Find output path from config
            schema_config = _get_schema_config(config, schema)
            output_path = f"outputs/{schema_config.name}.jsonl"
            click.echo(f"\n✨ Extraction complete! Results saved to: {output_path}")
            click.echo(f"  - View results:  cat {output_path} | head -n 5")
            click.echo(f"  - Refine schema: doc2json improve --schema {schema_config.name}")
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
def validate(schema):
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


@cli.command()
@click.option("--schema", "-s", help="Schema to generate suggestions for")
@click.option("--min-percent", default=20, help="Minimum percentage of docs a field must appear in (default: 20%)")
@click.option("--min-count", default=1, help="Minimum absolute count (default: 1)")
def improve(schema, min_percent: int, min_count: int):
    """Improve schema based on extraction feedback."""
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
            click.echo(f"❌ No suggestions file found at {suggestions_path}.", err=True)
            click.echo(f"Run 'doc2json extract --schema {schema_config.name} --assess' first.", err=True)
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
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
        )

        if not new_schema_code:
            click.echo("Failed to generate schema.")
            return

        # Write to new file
        suggested_path = f"schemas/{schema_config.name}_suggested.py"
        with open(suggested_path, "w") as f:
            f.write(new_schema_code)

        click.echo(f"\nWrote suggested schema to: {suggested_path}")

        # Show preview
        click.echo("\n--- Suggested schema preview ---")
        click.echo("---------------------------------")
        click.echo(new_schema_code[:2000] + ("\n..." if len(new_schema_code) > 2000 else ""))
        click.echo("---------------------------------")

        # Write to temporary file for review
        suggested_path = f"schemas/{schema_config.name}_suggested.py"
        with open(suggested_path, "w") as f:
            f.write(new_schema_code)

        click.echo(f"\n✨ Suggested schema wrote to: {suggested_path}")
        click.echo(f"Compare with original and run 'doc2json apply --schema {schema_config.name}' to accept.")

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


@cli.command()
@click.option("--schema", "-s", help="Schema to accept suggestion for")
def apply(schema):
    """Apply a suggested schema, versioning the current one."""
    try:
        config = load_config()
        schema_config = _get_schema_config(config, schema)
        _accept_schema_suggestion(config, schema_config.name)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument("name")
@click.option("--sample", "-f", type=click.Path(exists=True), help="Sample document to analyze")
def define(name, sample):
    """Design a new Pydantic schema interactively."""
    from doc2json.core.schema_generator import design_initial_schema
    from doc2json.core.archetypes import ARCHETYPES
    from doc2json.core.parsers import parse_document
    from doc2json.core.utils.fs import ensure_directory

    try:
        config = load_config()
        llm_config = config.llm

        click.echo(f"\n--- Designing schema for '{name}' ---")

        # 1. Start with Archetype
        archetype = None
        available_archetypes = list(ARCHETYPES.keys())
        click.echo(f"\n[1/5] Select a document archetype to guide design:")
        for i, arch in enumerate(available_archetypes, 1):
            desc = ARCHETYPES[arch]["description"]
            click.echo(f"  {i}. {arch} - {desc}")
        click.echo(f"  {len(available_archetypes) + 1}. Other (start from scratch)")

        choice = click.prompt("\nSelect an archetype", type=int, default=len(available_archetypes) + 1)
        
        doc_type = ""
        if 0 < choice <= len(available_archetypes):
            archetype = available_archetypes[choice - 1]
            doc_type = archetype
            click.echo(f"Using archetype: {archetype}")
        else:
            # 2. Ask for document type ONLY if "Other" is selected
            doc_type = click.prompt("\n[2/5] What type of document is this? (e.g. Purchase Order, Legal Waiver)")

        # 3. Ask for specificity
        click.echo(f"\n[3/5] Add specificity:")
        specificity = click.prompt("Any specific domain, industry, or country context? (e.g. UK law, Real Estate, Healthcare)", default="General", show_default=True)

        # 4. Ask for description
        click.echo(f"\n[4/5] Describe requirements:")
        description = click.prompt("Briefly describe what information you want to extract")
        full_description = f"{description}. Context: {specificity}"

        # 5. Handle sample document
        sample_text = ""
        if sample:
            click.echo(f"\n[5/5] Parsing sample document: {sample}...")
            sample_text = parse_document(str(sample))
            click.echo(f"Extracted {len(sample_text)} characters.")
        else:
            click.echo(f"\n[5/5] No sample document provided. Proceeding with description only.")

        # 6. Generate schema
        click.echo("\n--- Generating Pydantic schema via LLM ---")
        click.echo("This may take a moment...")
        schema_code = design_initial_schema(
            document_type=doc_type,
            description=full_description,
            sample_text=sample_text,
            archetype=archetype,
            provider=llm_config.provider,
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
        )

        if not schema_code:
            click.echo("❌ Failed to generate schema code.")
            return

        # 7. Preview and Save
        click.echo("\n--- Generated Schema Preview ---")
        click.echo("--------------------------------")
        click.echo(schema_code)
        click.echo("--------------------------------")
        
        ensure_directory("schemas")
        schema_path = Path(f"schemas/{name}.py")
        
        if not click.confirm(f"\nSave this schema to {schema_path}?"):
            click.echo("Aborted. Schema not saved.")
            return

        if schema_path.exists():
            if not click.confirm(f"File {schema_path} already exists. Overwrite?"):
                click.echo("Aborted.")
                return

        schema_path.write_text(schema_code)
        click.echo(f"✅ Wrote schema to: {schema_path}")

        # 8. Initialize sources directory
        sources_path = Path(f"sources/{name}")
        if not sources_path.exists():
            if click.confirm(f"\nCreate sources directory {sources_path}?"):
                ensure_directory(str(sources_path))
                click.echo(f"Created {sources_path}")

        # 9. Add to config if not present
        if not config.get_schema(name):
            if click.confirm(f"\nAdd '{name}' to your doc2json.yml automatically?"):
                # Simple YAML injection
                with open("doc2json.yml", "r") as f:
                    lines = f.readlines()
                
                # Find the schemas: line
                new_lines = []
                found_schemas = False
                for line in lines:
                    new_lines.append(line)
                    if line.strip().startswith("schemas:"):
                        found_schemas = True
                        new_lines.append(f"  - name: {name}\n")
                
                if found_schemas:
                    with open("doc2json.yml", "w") as f:
                        f.writelines(new_lines)
                    click.echo(f"✅ Added '{name}' to doc2json.yml")
                else:
                    click.echo("\nCould not find 'schemas:' section in doc2json.yml. Please add manually:")
                    click.echo(f"schemas:\n  - name: {name}")
        
        click.echo("\n✨ Done! Ready for your first extraction.")
        click.echo("\nNext steps:")
        click.echo(f"  1. Edit your schema (if needed):  {schema_path}")
        click.echo(f"  2. Add documents to:             {sources_path}/")
        click.echo(f"  3. Run a dry-run test:           doc2json extract --schema {name} --dry-run")
        click.echo(f"  4. Start real extraction:        doc2json extract --schema {name}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


if __name__ == "__main__":
    cli()

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from doc2json.config.loader import Config, SchemaConfig, LargeDocStrategy
from doc2json.core.parsers import parse_document, get_registry
from doc2json.core.parsers.pdf import PDFParser
from doc2json.core.extraction import load_schema, get_schema_version, ExtractionEngine
from doc2json.core.schema_analysis import analyze_schema
from doc2json.core.exceptions import DocumentTooLargeError, EmptyDocumentError
from doc2json.models.result import ExtractionResult
from doc2json.models.document import DocumentInfo
from doc2json.models.metadata import ExtractionMetadata, RunMetadata, TokenUsage

# Import connectors to register them
import doc2json.connectors.sources  # noqa: F401
import doc2json.connectors.destinations  # noqa: F401
from doc2json.connectors import get_source, get_destination

logger = logging.getLogger(__name__)

# Files to skip when scanning source directories
SKIP_FILES = {".gitkeep", ".gitignore", ".DS_Store"}


class SchemaTool:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def run(self, schema_name: Optional[str] = None):
        """Main execution flow: Parse documents -> Extract -> Write JSONL.

        Args:
            schema_name: If provided, only run extraction for this schema.
                        If None, run all schemas.
        """
        schemas = self._get_schemas_to_run(schema_name)
        if not schemas:
            return

        self.logger.info(f"Running {len(schemas)} extraction(s)")

        for schema_config in schemas:
            self._run_extraction(schema_config)

    def _get_schemas_to_run(self, schema_name: Optional[str]) -> list[SchemaConfig]:
        """Get list of schemas to run based on optional filter."""
        if schema_name:
            schema_config = self.config.get_schema(schema_name)
            if not schema_config:
                available = [s.name for s in self.config.schemas]
                self.logger.error(
                    f"Schema '{schema_name}' not found. "
                    f"Available: {', '.join(available)}"
                )
                return []
            return [schema_config]
        return self.config.schemas

    def _run_extraction(self, schema_config: SchemaConfig):
        """Run a single extraction pipeline."""
        llm_config = self.config.llm
        schema_name = schema_config.name

        self.logger.info(f"Loading schema: {schema_name}")
        schema_class = load_schema(schema_name)
        schema_version = get_schema_version(schema_name)
        self.logger.info(f"Schema version: {schema_version}")

        # Initialize extraction engine
        engine = ExtractionEngine(
            provider=llm_config.provider,
            model=llm_config.model,
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            api_version=llm_config.api_version,
        )

        # Get source and destination connectors
        source_config = self.config.get_source_config(schema_config)
        dest_config = self.config.get_destination_config(schema_config)

        source = get_source(source_config.type, source_config.config)
        destination = get_destination(dest_config.type, dest_config.config)

        self.logger.info(f"Source: {source_config.type}")
        self.logger.info(f"Destination: {dest_config.type}")

        # Initialize run metadata
        run_meta = RunMetadata(
            schema_name=schema_name,
            schema_version=schema_version,
            started_at=datetime.now(),
            provider=llm_config.provider,
            model=llm_config.model,
        )

        results: list[ExtractionResult] = []
        
        # Connect to source and destination using context managers
        with source, destination:
            self.logger.info("Processing documents from source...")
            
            # Process each document
            for doc_ref in source.iter_documents():
                self.logger.info(f"Processing: {doc_ref.name}")
                file_started = datetime.now()
                extract_tokens = None
                assess_tokens = None
                doc_info = None
                was_truncated = False
                error_msg = None

                try:
                    # Get local path for document (download if needed)
                    file_path = source.get_document_path(doc_ref)

                    # Parse document to text
                    text = parse_document(str(file_path))

                    # Validate document has content
                    if not text or not text.strip():
                        raise EmptyDocumentError(
                            f"Document has no extractable text content: {doc_ref.name}",
                            file_path=str(file_path)
                        )

                    # Get document info and apply size strategy
                    doc_info = self._get_document_info(str(file_path), text)
                    text, was_truncated = self._apply_size_strategy(
                        text, doc_info, schema_config
                    )

                    # Extract structured data with metadata
                    extract_response = engine.extract_with_metadata(text, schema_class)
                    extracted = extract_response.data
                    extract_tokens = extract_response.tokens

                    # Build result
                    result = ExtractionResult(
                        source_file=doc_ref.name,
                        schema_name=schema_name,
                        schema_version=schema_version,
                        data=extracted.model_dump(mode="json"),
                        truncated=was_truncated,
                        original_chars=doc_info.char_count if was_truncated else None,
                    )

                    # Optionally assess the extraction
                    if schema_config.assess:
                        self.logger.info(f"Assessing: {doc_ref.name}")
                        assess_response = engine.assess_with_metadata(
                            text, schema_class, extracted
                        )
                        result.assessment = assess_response.assessment
                        assess_tokens = assess_response.tokens
                        self.logger.info(
                            f"Review status: {assess_response.assessment.review_status.value}"
                        )

                    results.append(result)
                    run_meta.files_succeeded += 1
                    self.logger.info(f"Successfully extracted: {doc_ref.name}")

                    # Write record to destination
                    destination.write_record(result.to_output_dict())

                except DocumentTooLargeError as e:
                    error_msg = str(e)
                    self.logger.error(
                        f"Document too large: {doc_ref.name} "
                        f"({e.char_count:,} chars, limit: {e.max_chars:,})"
                    )
                    run_meta.files_failed += 1

                except EmptyDocumentError as e:
                    error_msg = str(e)
                    self.logger.warning(
                        f"Empty document skipped: {doc_ref.name} "
                        f"(no extractable text content)"
                    )
                    run_meta.files_failed += 1

                except Exception as e:
                    error_msg = str(e)
                    self.logger.error(f"Failed to process {doc_ref.name}: {e}")
                    run_meta.files_failed += 1

                # Record per-file metadata
                file_completed = datetime.now()
                file_meta = ExtractionMetadata(
                    source_file=doc_ref.name,
                    started_at=file_started,
                    completed_at=file_completed,
                    success=error_msg is None,
                    char_count=doc_info.char_count if doc_info else 0,
                    page_count=doc_info.page_count if doc_info else None,
                    truncated=was_truncated,
                    provider=llm_config.provider,
                    model=llm_config.model,
                    extract_tokens=extract_tokens,
                    assess_tokens=assess_tokens,
                    error=error_msg,
                )
                run_meta.extractions.append(file_meta)
                run_meta.files_processed += 1

            # Finalize run metadata
            run_meta.completed_at = datetime.now()

            # Write metadata
            destination.write_metadata(run_meta.to_summary_dict())
            for extraction in run_meta.extractions:
                destination.write_metadata({"_type": "extraction", **extraction.to_dict()})

            self.logger.info(f"Wrote {len(results)} records to destination")
            self.logger.info(
                f"Token usage: {run_meta.total_input_tokens:,} input, "
                f"{run_meta.total_output_tokens:,} output, "
                f"{run_meta.total_tokens:,} total"
            )

            self.logger.info(f"Wrote {len(results)} records to destination")
            self.logger.info(
                f"Token usage: {run_meta.total_input_tokens:,} input, "
                f"{run_meta.total_output_tokens:,} output, "
                f"{run_meta.total_tokens:,} total"
            )

        # Summary of review statuses if assessment enabled
        if schema_config.assess:
            self._print_assessment_summary(results, schema_name)

    def _get_source_files(self, sources_path: Path) -> list[Path]:
        """Get list of source files, handling both files and directories recursively."""
        source_files = []
        for item in sources_path.iterdir():
            if item.is_file() and item.name not in SKIP_FILES:
                source_files.append(item)
            elif item.is_dir():
                # Recursively get files from subdirectories
                source_files.extend(self._get_source_files(item))
        return source_files

    def _get_document_info(self, file_path: str, text: str) -> DocumentInfo:
        """Get document metadata including size and page count."""
        page_count = None

        # Try to get page count for PDFs
        if file_path.lower().endswith(".pdf"):
            try:
                pdf_parser = PDFParser()
                page_count = pdf_parser.get_page_count(file_path)
            except Exception:
                pass  # Page count is optional

        return DocumentInfo(
            file_path=file_path,
            char_count=len(text),
            page_count=page_count,
        )

    def _apply_size_strategy(
        self, text: str, doc_info: DocumentInfo, schema_config: SchemaConfig
    ) -> Tuple[str, bool]:
        """Apply the configured strategy for large documents.

        Args:
            text: The parsed document text
            doc_info: Document metadata
            schema_config: Schema configuration with strategy settings

        Returns:
            Tuple of (processed_text, was_truncated)

        Raises:
            DocumentTooLargeError: If strategy is FAIL and doc exceeds limit
        """
        max_chars = schema_config.max_chars
        strategy = schema_config.large_doc_strategy

        # Log if document is large
        if doc_info.is_large:
            self.logger.warning(
                f"Large document detected: {doc_info} "
                f"(strategy: {strategy.value})"
            )

        # Check if we need to do anything
        if not doc_info.exceeds_limit(max_chars):
            return text, False

        # Apply strategy
        if strategy == LargeDocStrategy.FULL:
            # Send full document anyway (user's choice)
            self.logger.warning(
                f"Document exceeds {max_chars:,} chars but sending full "
                f"(large_doc_strategy=full)"
            )
            return text, False

        elif strategy == LargeDocStrategy.TRUNCATE:
            # Truncate to max_chars
            self.logger.warning(
                f"Truncating document from {doc_info.char_count:,} to {max_chars:,} chars"
            )
            truncated_text = text[:max_chars]
            # Add marker so LLM knows content was cut
            truncated_text += "\n\n[... document truncated due to size limits ...]"
            return truncated_text, True

        elif strategy == LargeDocStrategy.FAIL:
            raise DocumentTooLargeError(
                f"Document exceeds size limit ({doc_info.char_count:,} chars > {max_chars:,} max). "
                f"Set large_doc_strategy to 'truncate' or 'full' to process anyway.",
                char_count=doc_info.char_count,
                max_chars=max_chars,
            )

        # Should never reach here
        return text, False

    def _write_metadata(self, meta_path: Path, run_meta: RunMetadata):
        """Write metadata to a .meta.jsonl file.

        Format:
        - Line 1: Run summary (schema, model, totals)
        - Lines 2+: Per-file extraction metadata
        """
        with open(meta_path, "w") as f:
            # Write run summary first
            f.write(json.dumps(run_meta.to_summary_dict()) + "\n")

            # Write per-file metadata
            for extraction in run_meta.extractions:
                record = {"_type": "extraction", **extraction.to_dict()}
                f.write(json.dumps(record) + "\n")

        self.logger.info(f"Wrote metadata to {meta_path}")

        # Log summary
        self.logger.info(
            f"Token usage: {run_meta.total_input_tokens:,} input, "
            f"{run_meta.total_output_tokens:,} output, "
            f"{run_meta.total_tokens:,} total"
        )

    def _print_assessment_summary(self, results: list[ExtractionResult], schema_name: str):
        """Print summary of assessment results and save suggestions to sidecar file."""
        from collections import Counter

        # Count review statuses
        status_counts: dict[str, int] = {}
        for r in results:
            if r.assessment:
                status = r.assessment.review_status.value
                status_counts[status] = status_counts.get(status, 0) + 1
        if status_counts:
            self.logger.info(f"Review summary: {status_counts}")

        # Collect per-document suggestions with full context
        docs_with_suggestions = []
        field_counts: Counter[str] = Counter()

        for r in results:
            if r.assessment and r.assessment.schema_suggestions:
                doc_suggestions = []
                for suggestion in r.assessment.schema_suggestions:
                    field_counts[suggestion.name] += 1
                    doc_suggestions.append(suggestion.model_dump())

                docs_with_suggestions.append({
                    "source_file": r.source_file,
                    "review_status": r.assessment.review_status.value,
                    "suggestions": doc_suggestions,
                })

        if field_counts:
            total_docs = len(results)
            docs_assessed = sum(1 for r in results if r.assessment)

            print("\n--- Schema Suggestions ---")
            for field_name, count in field_counts.most_common():
                pct = (count / docs_assessed * 100) if docs_assessed else 0
                print(f"  [{count}/{docs_assessed} = {pct:.0f}%] {field_name}")
            print()

            # Write rich suggestions to sidecar file for suggest-schema command
            suggestions_data = {
                "schema_name": schema_name,
                "total_documents": total_docs,
                "documents_assessed": docs_assessed,
                "documents_with_suggestions": len(docs_with_suggestions),
                "field_summary": {
                    name: {
                        "count": count,
                        "percentage": round(count / docs_assessed * 100, 1) if docs_assessed else 0,
                    }
                    for name, count in field_counts.items()
                },
                "documents": docs_with_suggestions,
            }

            suggestions_path = Path(f"outputs/{schema_name}_suggestions.json")
            suggestions_path.parent.mkdir(parents=True, exist_ok=True)
            with open(suggestions_path, "w") as f:
                json.dump(suggestions_data, f, indent=2)
            self.logger.info(f"Saved suggestions to {suggestions_path}")

    def dry_run(self, schema_name: Optional[str] = None):
        """Analyze schemas and documents without calling LLM.

        Shows schema analysis (fields, enums, nested models) and
        document sizes with token estimates.
        """
        schemas = self._get_schemas_to_run(schema_name)
        if not schemas:
            return

        for schema_config in schemas:
            self._dry_run_schema(schema_config)

    def _dry_run_schema(self, schema_config: SchemaConfig):
        """Run dry-run analysis for a single schema."""
        schema_name = schema_config.name

        # Load and analyze schema
        print(f"\n{'='*60}")
        print(f"Schema: {schema_name}")
        print(f"{'='*60}")

        try:
            schema_class = load_schema(schema_name)
            schema_version = get_schema_version(schema_name)
        except Exception as e:
            print(f"  ERROR: Could not load schema: {e}")
            return

        # Schema analysis
        analysis = analyze_schema(schema_class, name=schema_name)
        print(f"\nSchema Analysis (v{schema_version}):")
        print(analysis.format_summary())

        # Configuration
        print(f"\nConfiguration:")
        print(f"  Sources: {schema_config.sources_path}")
        print(f"  Output: {schema_config.output_path}")
        print(f"  Large doc strategy: {schema_config.large_doc_strategy.value}")
        print(f"  Max chars: {schema_config.max_chars:,}")

        # Get source files
        sources_path = Path(schema_config.sources_path)
        if not sources_path.exists():
            print(f"\n  WARNING: Sources directory not found: {sources_path}")
            return

        source_files = self._get_source_files(sources_path)
        if not source_files:
            print(f"\n  WARNING: No files found in {sources_path}")
            return

        # Analyze each document
        print(f"\nDocuments ({len(source_files)} files):")

        total_chars = 0
        total_tokens = 0
        truncated_count = 0
        failed_count = 0

        for file_path in sorted(source_files):
            try:
                text = parse_document(str(file_path))
                doc_info = self._get_document_info(str(file_path), text)

                # Check if would be truncated
                would_truncate = doc_info.exceeds_limit(schema_config.max_chars)
                effective_chars = min(doc_info.char_count, schema_config.max_chars)
                effective_tokens = effective_chars // 4

                # Format status
                status = ""
                if would_truncate:
                    if schema_config.large_doc_strategy == LargeDocStrategy.FAIL:
                        status = " [WOULD FAIL]"
                        failed_count += 1
                    elif schema_config.large_doc_strategy == LargeDocStrategy.TRUNCATE:
                        status = " [TRUNCATE]"
                        truncated_count += 1

                # Format page info
                pages = f"{doc_info.page_count} pages, " if doc_info.page_count else ""

                print(f"  {file_path.name:<35} {pages}{doc_info.char_count:>8,} chars  ~{doc_info.estimated_tokens:>6,} tokens{status}")

                total_chars += effective_chars
                total_tokens += effective_tokens

            except Exception as e:
                print(f"  {file_path.name:<35} ERROR: {e}")
                failed_count += 1

        # Summary
        processable_files = len(source_files) - failed_count
        total_output_tokens = analysis.estimated_output_tokens * processable_files

        print(f"\nSummary:")
        print(f"  Total files: {len(source_files)}")
        print(f"  Estimated input tokens (total): ~{total_tokens:,}")
        print(f"  Estimated output tokens (per doc): ~{analysis.estimated_output_tokens:,}")
        print(f"  Estimated output tokens (total): ~{total_output_tokens:,}")
        if truncated_count > 0:
            print(f"  Files to be truncated: {truncated_count}")
        if failed_count > 0:
            print(f"  Files that would fail: {failed_count}")

    def preview(self, schema_name: Optional[str] = None):
        """Preview the schema(s) that will be used for extraction."""
        schemas = self._get_schemas_to_run(schema_name)

        for schema_config in schemas:
            self.logger.info(f"Loading schema: {schema_config.name}")
            schema_class = load_schema(schema_config.name)

            print(f"\n{'='*50}")
            print(f"Schema: {schema_config.name}")
            print(f"Sources: {schema_config.sources_path}")
            print(f"Output: {schema_config.output_path}")
            print(f"\nSchema fields:")
            print(json.dumps(schema_class.model_json_schema(), indent=2))

    def test(self, schema_name: Optional[str] = None):
        """Run consistency tests for schema configs."""
        schemas = self._get_schemas_to_run(schema_name)
        all_passed = True

        for schema_config in schemas:
            print(f"\n--- Testing: {schema_config.name} ---")

            # Test 1: Schema loads
            print(f"Testing schema load: {schema_config.name}...", end=" ")
            try:
                schema_class = load_schema(schema_config.name)
                print("OK")
            except Exception as e:
                print(f"FAILED: {e}")
                all_passed = False
                continue

            # Test 2: Sources directory exists
            print(f"Testing sources directory: {schema_config.sources_path}...", end=" ")
            sources_path = Path(schema_config.sources_path)
            if sources_path.exists():
                print("OK")
            else:
                print("FAILED: Directory not found")
                all_passed = False
                continue

            # Test 3: Can parse at least one file
            source_files = self._get_source_files(sources_path)
            if source_files:
                print(f"Testing parser for: {source_files[0].name}...", end=" ")
                try:
                    text = parse_document(str(source_files[0]))
                    print(f"OK ({len(text)} chars)")
                except Exception as e:
                    print(f"FAILED: {e}")
                    all_passed = False
                    continue
            else:
                print("No source files to test parsing")

        if all_passed:
            print("\nAll tests passed!")
        else:
            print("\nSome tests failed!")

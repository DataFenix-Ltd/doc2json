"""Main layout extraction orchestrator."""

import logging
import mimetypes
import os
from typing import Any, Dict, List, Optional

from .schema import LayoutDocument, LayoutElement, LayoutMetadata, LayoutPage, LayoutStyle

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Threshold for considering a PDF "digital" (has extractable text)
PDF_TEXT_THRESHOLD = 50


class LayoutExtractor:
    """Main orchestrator for layout extraction across different document types."""

    def __init__(self):
        pass

    def _is_digital_pdf(self, file_path: str) -> bool:
        """Check if PDF has extractable text (digital) or is scanned (image-based)."""
        if fitz is None:
            return False
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text = page.get_text()
                if len(text.strip()) > PDF_TEXT_THRESHOLD:
                    doc.close()
                    return True
            doc.close()
            return False
        except Exception:
            return False

    def process(
        self,
        file_path: str,
        vlm_client: Any = None,
        extraction_id: Optional[str] = None,
        debug_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point. Routes to correct engine based on file type.

        Args:
            file_path: Path to document (PDF, image, or HTML)
            vlm_client: Optional VLM client for style extraction
            extraction_id: Optional UUID to link layout with extraction record
            debug_dir: Optional directory to save debug images

        Returns:
            LayoutDocument as dict
        """
        self._debug_dir = debug_dir
        # Lazy imports to avoid loading heavy dependencies unless needed
        from .dom_engine import DomEngine
        from .pdf_engine import PdfEngine
        from .vision_engine import VisionEngine

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        mime_type, _ = mimetypes.guess_type(file_path)
        origin_type = "scanned_image"
        elements: List[LayoutElement] = []
        width, height = 0.0, 0.0
        page_count = 1

        logger.info(f"Processing layout for: {os.path.basename(file_path)}")

        # Route to appropriate engine based on file type
        if file_path.lower().endswith(".html") or mime_type == "text/html":
            origin_type = "html_render"
            logger.debug("Detected HTML file, using DOM engine")
            engine = DomEngine()
            elements = engine.detect(file_path)
            width, height = 1920, 1080  # Default viewport

        elif file_path.lower().endswith(".pdf") or mime_type == "application/pdf":
            if self._is_digital_pdf(file_path):
                origin_type = "digital_pdf"
                logger.debug("Detected digital PDF, using PDF engine")
                engine = PdfEngine()

                # Process all pages
                if fitz:
                    doc = fitz.open(file_path)
                    page_count = len(doc)
                    all_page_elements = engine.detect_all_pages(file_path)

                    # Build multi-page output
                    pages = []
                    for page_idx, page_elements in enumerate(all_page_elements):
                        pdf_page = doc[page_idx]
                        pages.append(LayoutPage(
                            page_no=page_idx + 1,
                            width=pdf_page.rect.width,
                            height=pdf_page.rect.height,
                            elements=page_elements
                        ))
                    doc.close()

                    # Return early with multi-page document
                    metadata = LayoutMetadata(
                        filename=os.path.basename(file_path),
                        page_count=page_count,
                        origin_type=origin_type,
                        extraction_id=extraction_id
                    )
                    total_elements = sum(len(p.elements) for p in pages)
                    logger.info(f"Detected {total_elements} layout elements across {page_count} pages ({origin_type})")

                    return LayoutDocument(metadata=metadata, pages=pages).model_dump()
            else:
                origin_type = "scanned_image"
                logger.debug("Detected scanned PDF, using Vision engine")
                # For scanned PDFs, we need to render to image first
                width, height = self._get_pdf_dimensions(file_path)
                engine = VisionEngine()
                elements = engine.detect(file_path, vlm_client=vlm_client, debug_dir=self._debug_dir)

        elif self._is_image_file(file_path):
            origin_type = "scanned_image"
            logger.debug("Detected image file, using Vision engine")
            engine = VisionEngine()
            elements = engine.detect(file_path, vlm_client=vlm_client, debug_dir=self._debug_dir)
            from PIL import Image
            with Image.open(file_path) as img:
                width, height = img.size

        else:
            logger.warning(f"Unsupported file type: {file_path}")
            origin_type = "skipped_unsupported"

        logger.info(f"Detected {len(elements)} layout elements ({origin_type})")

        # Construct output
        page = LayoutPage(
            page_no=1,
            width=width,
            height=height,
            elements=elements
        )

        metadata = LayoutMetadata(
            filename=os.path.basename(file_path),
            page_count=page_count,
            origin_type=origin_type,
            extraction_id=extraction_id
        )
        
        doc = LayoutDocument(
            metadata=metadata,
            pages=[page]
        )

        return doc.model_dump()

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is a supported image format."""
        valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
        ext = os.path.splitext(file_path)[1].lower()
        return ext in valid_extensions

    def _get_pdf_dimensions(self, file_path: str) -> tuple[float, float]:
        """Get dimensions of first page of a PDF."""
        if fitz is None:
            return 0.0, 0.0
        try:
            doc = fitz.open(file_path)
            if len(doc) > 0:
                page = doc[0]
                width, height = page.rect.width, page.rect.height
                doc.close()
                return width, height
            doc.close()
        except Exception as e:
            logger.warning(f"Could not get PDF dimensions: {e}")
        return 0.0, 0.0

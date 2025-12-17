"""PDF document parser with OCR fallback for scanned documents."""

import logging
import os
import shutil
from dataclasses import dataclass

import pdfplumber
import pdf2image
import pytesseract

from doc2json.core.exceptions import ParserError

logger = logging.getLogger(__name__)

# Minimum characters per page to consider it "text-based"
# Below this threshold, we assume it's a scanned/image PDF
MIN_CHARS_PER_PAGE = 50


@dataclass
class PDFPageResult:
    """Result of parsing a single PDF page."""
    page_num: int
    text: str
    used_ocr: bool


class PDFParser:
    """Parser for PDF files with automatic OCR fallback.

    Attempts text extraction first using pdfplumber. If a page has
    insufficient text (likely a scanned document), falls back to OCR
    using pytesseract.

    For OCR: Requires Tesseract installed on the system
    """

    SUPPORTED_EXTENSIONS = {".pdf"}

    def __init__(
        self,
        min_chars_per_page: int = MIN_CHARS_PER_PAGE,
        ocr_enabled: bool = True,
        ocr_language: str = "eng",
    ):
        """Initialize PDF parser.

        Args:
            min_chars_per_page: Threshold below which OCR is attempted
            ocr_enabled: Whether to attempt OCR for image-based pages
            ocr_language: Tesseract language code (e.g., 'eng', 'fra', 'deu')
        """
        self.min_chars_per_page = min_chars_per_page
        self.ocr_enabled = ocr_enabled
        self.ocr_language = ocr_language

    def can_parse(self, file_path: str) -> bool:
        """Check if this is a PDF file."""
        _, ext = os.path.splitext(file_path)
        return ext.lower() in self.SUPPORTED_EXTENSIONS

    def _check_tesseract(self):
        """Check if Tesseract is installed on the system."""
        if shutil.which("tesseract") is None:
            raise ParserError(
                "Tesseract OCR is not installed on your system. "
                "Install it with:\n"
                "  macOS: brew install tesseract\n"
                "  Ubuntu: sudo apt install tesseract-ocr\n"
                "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
            )

    def _extract_text_from_page(self, page) -> str:
        """Extract text from a pdfplumber page object."""
        text = page.extract_text() or ""
        return text.strip()

    def _ocr_page_image(self, image) -> str:
        """Run OCR on a PIL Image."""
        try:
            text = pytesseract.image_to_string(image, lang=self.ocr_language)
            return text.strip()
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

    def _convert_page_to_image(self, pdf_path: str, page_num: int):
        """Convert a single PDF page to an image.

        Args:
            pdf_path: Path to the PDF file
            page_num: 0-indexed page number

        Returns:
            PIL Image of the page
        """
        # pdf2image uses 1-indexed pages
        images = pdf2image.convert_from_path(
            pdf_path,
            first_page=page_num + 1,
            last_page=page_num + 1,
            dpi=300,  # Good quality for OCR
        )
        return images[0] if images else None

    def parse_page(self, pdf_path: str, page, page_num: int) -> PDFPageResult:
        """Parse a single page, using OCR if needed.

        Args:
            pdf_path: Path to the PDF file (needed for OCR)
            page: pdfplumber page object
            page_num: 0-indexed page number

        Returns:
            PDFPageResult with extracted text
        """
        # Try text extraction first
        text = self._extract_text_from_page(page)

        # Check if we got enough text
        if len(text) >= self.min_chars_per_page:
            return PDFPageResult(page_num=page_num, text=text, used_ocr=False)

        # Not enough text - this might be a scanned page
        if not self.ocr_enabled:
            logger.warning(
                f"Page {page_num + 1} has little text ({len(text)} chars) "
                f"but OCR is disabled"
            )
            return PDFPageResult(page_num=page_num, text=text, used_ocr=False)

        # Attempt OCR
        logger.info(f"Page {page_num + 1} appears to be scanned, attempting OCR...")
        try:
            self._check_tesseract()
            image = self._convert_page_to_image(pdf_path, page_num)
            if image:
                ocr_text = self._ocr_page_image(image)
                if ocr_text:
                    return PDFPageResult(page_num=page_num, text=ocr_text, used_ocr=True)
        except ParserError:
            raise
        except Exception as e:
            logger.warning(f"OCR failed for page {page_num + 1}: {e}")

        # Return whatever we got from text extraction
        return PDFPageResult(page_num=page_num, text=text, used_ocr=False)

    def parse(self, file_path: str) -> str:
        """Parse a PDF file and extract text from all pages.

        Args:
            file_path: Path to the PDF file

        Returns:
            Concatenated text from all pages

        Raises:
            ParserError: If PDF cannot be parsed
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        try:
            with pdfplumber.open(file_path) as pdf:
                results: list[PDFPageResult] = []
                ocr_pages = 0

                for page_num, page in enumerate(pdf.pages):
                    result = self.parse_page(file_path, page, page_num)
                    results.append(result)
                    if result.used_ocr:
                        ocr_pages += 1

                # Log summary
                total_pages = len(results)
                if ocr_pages > 0:
                    logger.info(
                        f"Parsed {total_pages} pages "
                        f"({ocr_pages} required OCR)"
                    )

                # Combine all page texts
                texts = [r.text for r in results if r.text]
                return "\n\n".join(texts)

        except Exception as e:
            if "pdfplumber" in str(type(e).__module__):
                raise ParserError(f"Failed to parse PDF: {e}")
            raise

    def get_page_count(self, file_path: str) -> int:
        """Get the number of pages in a PDF."""
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)

    def analyze(self, file_path: str) -> dict:
        """Analyze a PDF and return metadata about its content.

        Useful for understanding if a PDF is text-based or image-based
        before running full extraction.
        """
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            text_pages = 0
            image_pages = 0
            total_chars = 0

            for page in pdf.pages:
                text = self._extract_text_from_page(page)
                total_chars += len(text)
                if len(text) >= self.min_chars_per_page:
                    text_pages += 1
                else:
                    image_pages += 1

            return {
                "total_pages": total_pages,
                "text_pages": text_pages,
                "image_pages": image_pages,
                "total_characters": total_chars,
                "avg_chars_per_page": total_chars / total_pages if total_pages > 0 else 0,
                "likely_scanned": image_pages > text_pages,
                "ocr_recommended": image_pages > 0,
            }

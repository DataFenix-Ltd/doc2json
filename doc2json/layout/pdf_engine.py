"""PDF layout detection engine using PyMuPDF."""

import logging
from typing import List, Optional

from .schema import LayoutElement, LayoutPage, LayoutStyle
from .utils import color_int_to_hex, classify_color

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Font size threshold for detecting titles
TITLE_SIZE_THRESHOLD = 14


class PdfEngine:
    """Layout detection engine for digital PDFs with extractable text."""

    def __init__(self):
        if fitz is None:
            raise ImportError(
                "pymupdf is not installed.\n"
                "Install with: pip install doc2json[layout]"
            )

    def detect(self, file_path: str, page_num: Optional[int] = None) -> List[LayoutElement]:
        """
        Detect layout elements in a PDF.

        Args:
            file_path: Path to PDF file
            page_num: Optional specific page number (0-indexed). If None, processes first page only.

        Returns:
            List of LayoutElement for the specified page
        """
        doc = fitz.open(file_path)
        target_page = page_num if page_num is not None else 0

        if target_page >= len(doc):
            logger.warning(f"Page {target_page} out of range (PDF has {len(doc)} pages)")
            doc.close()
            return []

        page = doc[target_page]
        results = self._extract_page_elements(page, element_id_start=1)
        doc.close()

        logger.debug(f"Extracted {len(results)} elements from page {target_page + 1}")
        return results

    def detect_all_pages(self, file_path: str) -> List[List[LayoutElement]]:
        """
        Detect layout elements for all pages in a PDF.

        Returns:
            List of element lists, one per page
        """
        doc = fitz.open(file_path)
        all_pages = []
        element_id = 1

        for page_idx, page in enumerate(doc):
            elements = self._extract_page_elements(page, element_id_start=element_id)
            all_pages.append(elements)
            element_id += len(elements)
            logger.debug(f"Page {page_idx + 1}: {len(elements)} elements")

        doc.close()
        return all_pages

    def _extract_page_elements(self, page, element_id_start: int = 1) -> List[LayoutElement]:
        """Extract layout elements from a single PDF page."""
        results = []
        element_id = element_id_start

        # get_text("dict") provides structure: block -> line -> span
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            bbox = list(block["bbox"])

            # Image block (type 1)
            if block["type"] == 1:
                results.append(LayoutElement(
                    id=element_id,
                    category="Picture",
                    bbox=bbox,
                    text_content=None
                ))
                element_id += 1
                continue

            # Text block (type 0)
            if "lines" not in block:
                continue

            # Aggregate text and style info from spans
            full_text = []
            fonts = []
            sizes = []
            colors = []
            flags_list = []

            for line in block["lines"]:
                for span in line["spans"]:
                    full_text.append(span["text"])
                    fonts.append(span["font"])
                    sizes.append(span["size"])
                    colors.append(span["color"])
                    flags_list.append(span.get("flags", 0))

            text_content = " ".join(full_text).strip()
            if not text_content:
                continue

            # Dominant style (take first span's style)
            dominant_font = fonts[0] if fonts else "unknown"
            dominant_size = sizes[0] if sizes else 0.0
            dominant_color = colors[0] if colors else 0
            dominant_flags = flags_list[0] if flags_list else 0

            # Infer font category
            f_cat = "unknown"
            lower_font = dominant_font.lower()
            if "serif" in lower_font or "times" in lower_font:
                f_cat = "serif"
            elif "sans" in lower_font or "arial" in lower_font or "helvetica" in lower_font:
                f_cat = "sans"
            elif "mono" in lower_font or "courier" in lower_font:
                f_cat = "mono"

            # Infer weight from font name or flags
            # PyMuPDF flags: bit 0 = superscript, bit 1 = italic, bit 2 = bold
            is_bold = bool(dominant_flags & 4) or "bold" in lower_font
            weight = "bold" if is_bold else "normal"

            # Infer font style (italic)
            is_italic = bool(dominant_flags & 2) or "italic" in lower_font or "oblique" in lower_font
            font_style = "italic" if is_italic else "normal"

            # Convert color to hex and classify
            text_color_hex = color_int_to_hex(dominant_color)
            text_color_class = classify_color(text_color_hex)

            style_obj = LayoutStyle(
                font_category=f_cat,
                typeface_name=dominant_font,
                font_weight=weight,
                font_style=font_style,
                font_size=dominant_size,
                text_color_hex=text_color_hex,
                text_color_class=text_color_class,
            )

            # Categorize by size
            category = "Title" if dominant_size > TITLE_SIZE_THRESHOLD else "Text"

            results.append(LayoutElement(
                id=element_id,
                category=category,
                bbox=bbox,
                text_content=text_content,
                style=style_obj
            ))
            element_id += 1

        return results

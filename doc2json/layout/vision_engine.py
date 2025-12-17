"""Vision-based layout detection engine using Surya OCR."""

import logging
from typing import List, Optional

from PIL import Image

from .schema import LayoutElement, LayoutStyle
from .som_utils import draw_som_overlay

logger = logging.getLogger(__name__)

try:
    from surya.layout import LayoutPredictor
    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor
    from surya.detection import DetectionPredictor
    SURYA_AVAILABLE = True
except ImportError:
    SURYA_AVAILABLE = False

# Standard category mapping for consistency across engines
CATEGORY_MAP = {
    # Surya labels -> standard categories
    "Title": "Title",
    "Section-header": "Title",
    "Page-header": "Header",
    "Page-footer": "Footer",
    "Text": "Text",
    "List-item": "List-item",
    "Table": "Table",
    "Figure": "Picture",
    "Picture": "Picture",
    "Caption": "Caption",
    "Formula": "Formula",
    "Footnote": "Footnote",
    "Code": "Code",
}


class VisionEngine:
    """Layout detection engine for scanned documents and images using Surya OCR."""

    def __init__(self):
        if not SURYA_AVAILABLE:
            raise ImportError(
                "surya-ocr is not installed.\n"
                "Install with: pip install doc2json[layout]"
            )
        # Lazy-loaded models
        self._foundation_predictor = None
        self._layout_predictor = None
        self._recognition_predictor = None
        self._detection_predictor = None

    def _ensure_models_loaded(self):
        """Lazy load the Surya models (they're heavy)."""
        if self._foundation_predictor is None:
            logger.info("Loading Surya layout models (this may take a moment)...")
            self._foundation_predictor = FoundationPredictor()
            self._layout_predictor = LayoutPredictor(self._foundation_predictor)
            logger.info("Surya layout models loaded")

    def _ensure_ocr_models_loaded(self):
        """Lazy load the Surya OCR models."""
        if self._foundation_predictor is None:
            logger.info("Loading Surya foundation model...")
            self._foundation_predictor = FoundationPredictor()
        if self._recognition_predictor is None:
            logger.info("Loading Surya OCR models...")
            self._detection_predictor = DetectionPredictor()
            self._recognition_predictor = RecognitionPredictor(self._foundation_predictor)
            logger.info("Surya OCR models loaded")

    def detect(
        self,
        image_path: str,
        vlm_client=None,
        extract_text: bool = True,
        debug_dir: str = None
    ) -> List[LayoutElement]:
        """
        Detect layout elements in an image.

        Args:
            image_path: Path to image file (PNG, JPG, etc.)
            vlm_client: Optional VLM client for style extraction
            extract_text: Whether to run OCR for text extraction (default: True)
            debug_dir: Optional directory to save debug images (bounding boxes, etc.)

        Returns:
            List of LayoutElement with bounding boxes, text content, and optional styles
        """
        self._ensure_ocr_models_loaded()

        image = Image.open(image_path).convert("RGB")
        logger.info(f"Processing image: {image_path} ({image.size[0]}x{image.size[1]})")

        self._debug_dir = debug_dir

        # Use OCR detection directly - it gives better granularity than layout detection
        # Surya's layout model often returns too few boxes for documents
        logger.info("Running OCR to detect text regions...")
        predictions = self._recognition_predictor(
            [image],
            det_predictor=self._detection_predictor
        )

        layout_elements = []
        som_elements = []

        if predictions and len(predictions) > 0:
            ocr_result = predictions[0]
            logger.info(f"OCR detected {len(ocr_result.text_lines)} text lines")

            for idx, line in enumerate(ocr_result.text_lines):
                if not hasattr(line, 'bbox') or not line.bbox:
                    continue

                bbox = [float(x) for x in line.bbox]
                text = line.text.strip() if hasattr(line, 'text') and line.text else None

                # Infer category from text content
                category = self._infer_category(text, bbox, image.size)

                element = LayoutElement(
                    id=idx + 1,
                    category=category,
                    bbox=bbox,
                    confidence=getattr(line, 'confidence', 1.0),
                    text_content=text
                )
                layout_elements.append(element)

                # Prepare for SoM overlay
                som_elements.append({
                    "id": element.id,
                    "bbox": element.bbox
                })

        # Save debug images if requested
        if debug_dir:
            self._save_debug_images(image, layout_elements, image_path)

        # Style extraction via VLM (optional)
        if vlm_client and som_elements:
            logger.info(f"Extracting styles for {len(som_elements)} elements via VLM...")
            styles = self._extract_styles_with_vlm(image, som_elements, vlm_client)

            # Merge styles into elements
            for element in layout_elements:
                if element.id in styles:
                    element.style = styles[element.id]

            logger.debug(f"Applied styles to {len(styles)} elements")

        return layout_elements

    def _infer_category(self, text: str, bbox: List[float], image_size: tuple) -> str:
        """Infer element category from text content and position."""
        if not text:
            return "Text"

        # Clean HTML-like tags from Surya output
        clean_text = text.replace("<b>", "").replace("</b>", "").strip()

        # Check for title-like characteristics
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        img_width, img_height = image_size

        # Large text near top = likely title
        if y1 < img_height * 0.15 and height > 20:
            return "Title"

        # Bold tags often indicate headers
        if "<b>" in text and len(clean_text) < 50:
            return "Title"

        # All caps short text = likely header
        if clean_text.isupper() and len(clean_text) < 30:
            return "Title"

        # Currency/numbers at end of line = likely table data
        if any(c in text for c in ["$", "£", "€"]) or text.replace(",", "").replace(".", "").isdigit():
            return "Text"  # Could be "Table" but we don't have full table detection

        # List items
        if clean_text.startswith(("•", "-", "*", "·")) or (len(clean_text) > 2 and clean_text[0].isdigit() and clean_text[1] in ".):"):
            return "List-item"

        return "Text"

    def _save_debug_images(self, image: Image.Image, elements: List[LayoutElement], image_path: str) -> None:
        """Save debug images showing bounding boxes and detected text."""
        import os
        from PIL import ImageDraw, ImageFont

        debug_dir = self._debug_dir
        os.makedirs(debug_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(image_path))[0]

        # Create a copy for drawing
        debug_img = image.copy()
        draw = ImageDraw.Draw(debug_img)

        # Try to get a font, fall back to default
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
        except:
            font = ImageFont.load_default()
            small_font = font

        # Color map for categories
        colors = {
            "Title": "#FF0000",      # Red
            "Text": "#00FF00",       # Green
            "Picture": "#0000FF",    # Blue
            "Table": "#FF00FF",      # Magenta
            "List-item": "#00FFFF",  # Cyan
            "Header": "#FFA500",     # Orange
            "Footer": "#FFA500",     # Orange
            "Caption": "#FFFF00",    # Yellow
        }

        for element in elements:
            x1, y1, x2, y2 = element.bbox
            color = colors.get(element.category, "#888888")

            # Draw bounding box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # Draw label with ID and category
            label = f"{element.id}: {element.category}"
            draw.rectangle([x1, y1 - 18, x1 + len(label) * 7, y1], fill=color)
            draw.text((x1 + 2, y1 - 16), label, fill="white", font=small_font)

            # Draw text content preview (first 30 chars)
            if element.text_content:
                preview = element.text_content[:30] + "..." if len(element.text_content) > 30 else element.text_content
                draw.text((x1 + 2, y2 + 2), preview, fill=color, font=small_font)

        # Save layout boxes image
        layout_path = os.path.join(debug_dir, f"{base_name}_layout.png")
        debug_img.save(layout_path)
        logger.info(f"Saved debug image: {layout_path}")

        # Also save a legend
        legend_path = os.path.join(debug_dir, f"{base_name}_legend.txt")
        with open(legend_path, "w") as f:
            f.write("Layout Detection Debug\n")
            f.write("=" * 40 + "\n\n")
            for element in elements:
                f.write(f"ID {element.id}: {element.category}\n")
                f.write(f"  BBox: {element.bbox}\n")
                if element.text_content:
                    f.write(f"  Text: {element.text_content[:100]}...\n" if len(element.text_content) > 100 else f"  Text: {element.text_content}\n")
                f.write("\n")
        logger.info(f"Saved legend: {legend_path}")

    def _extract_styles_with_vlm(
        self,
        image: Image.Image,
        som_elements: List[dict],
        vlm_client
    ) -> dict:
        """Extract styles using Set-of-Mark + VLM pipeline."""
        try:
            # Draw SoM overlay (numbered boxes)
            som_image = draw_som_overlay(image, som_elements)
            logger.debug(f"Created SoM overlay image")

            # Call VLM
            element_ids = [e["id"] for e in som_elements]
            styles = vlm_client.extract_styles(som_image, element_ids)

            return styles

        except Exception as e:
            logger.error(f"VLM style extraction failed: {e}")
            return {}

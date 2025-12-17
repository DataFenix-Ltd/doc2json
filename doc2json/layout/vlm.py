"""VLM (Vision Language Model) clients for style extraction."""

import base64
import io
import logging
from typing import Dict, List, Optional, Protocol, Literal

from PIL import Image
from pydantic import BaseModel, Field

from .schema import LayoutStyle

logger = logging.getLogger(__name__)


class ElementStyleResponse(BaseModel):
    """Style attributes for a single element extracted by VLM."""

    font_category: Literal["serif", "sans", "mono", "handwritten", "display", "unknown"] = Field(
        default="unknown",
        description="General category of the font family"
    )
    typeface_name: Optional[str] = Field(
        default=None,
        description="Specific typeface name if identifiable (e.g., 'Arial', 'Helvetica', 'Times New Roman')"
    )
    font_weight: Literal["thin", "light", "normal", "medium", "semibold", "bold", "extrabold", "black", "unknown"] = Field(
        default="unknown",
        description="Visual weight of the font"
    )
    font_style: Literal["normal", "italic", "oblique", "unknown"] = Field(
        default="unknown",
        description="Font style (normal, italic, oblique)"
    )
    font_size: Optional[float] = Field(
        default=None,
        description="Estimated font size in points"
    )
    text_color_hex: Optional[str] = Field(
        default=None,
        description="Text color as hex code (e.g., '#000000')"
    )
    text_color_class: Literal["black", "gray", "white", "red", "blue", "green", "yellow", "orange", "purple", "other", "unknown"] = Field(
        default="unknown",
        description="Dominant color category of the text"
    )
    background_color: Optional[str] = Field(
        default=None,
        description="Background color as hex code if highlighted"
    )
    alignment: Literal["left", "center", "right", "justify", "unknown"] = Field(
        default="unknown",
        description="Horizontal text alignment"
    )


class StyleExtractionResponse(BaseModel):
    """Response containing styles for all requested elements."""

    elements: Dict[str, ElementStyleResponse] = Field(
        description="Map of element ID (as string) to its style attributes"
    )


class VLMClient(Protocol):
    """Protocol for VLM clients that extract styles from images."""

    def extract_styles(self, image: Image.Image, ids: List[int]) -> Dict[int, LayoutStyle]:
        """Extract styles for the given element IDs from a SoM-annotated image."""
        ...


class GeminiVLMClient:
    """Gemini-based VLM client for style extraction using Instructor."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        try:
            import google.generativeai as genai
            import instructor
        except ImportError as e:
            raise ImportError(
                "google-generativeai and instructor are required.\n"
                "Install with: pip install doc2json[layout] instructor"
            ) from e

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)
        self._client = instructor.from_gemini(self._model)
        self._model_name = model_name
        logger.info(f"Initialized Gemini VLM client with model: {model_name}")

    def extract_styles(self, image: Image.Image, ids: List[int]) -> Dict[int, LayoutStyle]:
        """
        Extract styles for elements using Instructor for structured output.

        Args:
            image: PIL Image with Set-of-Mark annotations (numbered boxes)
            ids: List of element IDs to extract styles for

        Returns:
            Dict mapping element ID to LayoutStyle
        """
        logger.info(f"Extracting styles for {len(ids)} elements via VLM...")

        # Convert image to base64 for Gemini
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_bytes = buffered.getvalue()

        prompt = f"""Analyze this document image with numbered green ID tags marking text elements.

For each of these element IDs: {ids}

Extract the visual typography style by examining the text appearance at each numbered marker.

Focus on:
- Font category (serif, sans-serif, monospace, etc.)
- Font weight (normal, bold, etc.)
- Text color
- Alignment if discernible

Return styles for ALL requested IDs."""

        try:
            logger.info(f"Calling Gemini API ({self._model_name})...")

            response = self._client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
                                }
                            }
                        ]
                    }
                ],
                response_model=StyleExtractionResponse,
            )

            logger.info(f"Received structured response with {len(response.elements)} elements")

            # Convert to LayoutStyle objects
            results = {}
            for str_id, style_resp in response.elements.items():
                try:
                    element_id = int(str_id)
                    results[element_id] = LayoutStyle(
                        font_category=style_resp.font_category,
                        typeface_name=style_resp.typeface_name,
                        font_weight=style_resp.font_weight,
                        font_style=style_resp.font_style,
                        font_size=style_resp.font_size,
                        text_color_hex=style_resp.text_color_hex,
                        text_color_class=style_resp.text_color_class,
                        background_color=style_resp.background_color,
                        alignment=style_resp.alignment,
                    )
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse style for ID {str_id}: {e}")

            return results

        except Exception as e:
            logger.error(f"VLM style extraction failed: {e}")
            return {}

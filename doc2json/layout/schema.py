from typing import List, Optional, Tuple, Literal
from pydantic import BaseModel, Field

class LayoutStyle(BaseModel):
    """
    Visual style attributes for a layout element.
    Extracted via Code (DOM/PDF) or VLM (Vision).
    """
    # Font Information
    font_category: Literal["serif", "sans", "mono", "handwritten", "display", "unknown"] = Field(
        default="unknown",
        description="General category of the font family."
    )
    typeface_name: Optional[str] = Field(
        default=None,
        description="Specific typeface/font name if identifiable (e.g., 'Arial', 'Times New Roman', 'Helvetica')."
    )
    font_weight: Literal["thin", "light", "normal", "medium", "semibold", "bold", "extrabold", "black", "unknown"] = Field(
        default="unknown",
        description="Visual weight of the font."
    )
    font_style: Literal["normal", "italic", "oblique", "unknown"] = Field(
        default="unknown",
        description="Font style (normal, italic, oblique)."
    )
    font_size: Optional[float] = Field(
        default=None, 
        description="Font size in points (approximate for vision)."
    )
    
    # Color Information
    text_color_hex: Optional[str] = Field(
        default=None,
        description="Precise text color as hex code (e.g., '#000000')."
    )
    text_color_class: Literal["black", "gray", "white", "red", "blue", "green", "yellow", "orange", "purple", "other", "unknown"] = Field(
        default="unknown",
        description="Dominant color category of the text."
    )
    background_color: Optional[str] = Field(
        default=None, 
        description="Hex code of background if relevant (e.g. highlight)."
    )
    
    # Layout & Spacing
    alignment: Literal["left", "center", "right", "justify", "unknown"] = Field(
        default="unknown",
        description="Horizontal alignment of the text."
    )
    letter_spacing: Literal["tight", "normal", "loose", "unknown"] = Field(
        default="unknown",
        description="Visual letter spacing / tracking."
    )
    line_height: Literal["tight", "normal", "loose", "unknown"] = Field(
        default="unknown",
        description="Visual line height / leading."
    )
    
    # Text Decoration
    text_decoration: Optional[List[Literal["underline", "strikethrough", "overline"]]] = Field(
        default=None,
        description="Text decorations present (underline, strikethrough, etc.)."
    )
    text_transform: Literal["uppercase", "lowercase", "capitalize", "normal", "unknown"] = Field(
        default="unknown",
        description="Text case transformation."
    )

class LayoutElement(BaseModel):
    id: int
    category: str = Field(..., description="DocLayNet category (e.g. Title, Table, Text)")
    bbox: Tuple[float, float, float, float] = Field(..., description="[x_min, y_min, x_max, y_max]")
    confidence: float = Field(default=1.0, description="Confidence score 0.0-1.0")
    text_content: Optional[str] = None
    style: Optional[LayoutStyle] = None

class LayoutPage(BaseModel):
    page_no: int
    width: float
    height: float
    elements: List[LayoutElement] = []

class LayoutMetadata(BaseModel):
    filename: str
    page_count: int
    origin_type: Literal["digital_pdf", "scanned_image", "html_render", "skipped_unsupported"]
    extraction_id: Optional[str] = Field(
        default=None,
        description="UUID linking to the corresponding extraction record"
    )

class LayoutDocument(BaseModel):
    metadata: LayoutMetadata
    pages: List[LayoutPage]

"""Shared utilities for layout extraction engines."""

import re
from typing import Optional


def color_int_to_hex(color_int: int) -> str:
    """Convert PyMuPDF color integer to hex string.

    Args:
        color_int: RGB color packed as integer (PyMuPDF format)

    Returns:
        Hex color string (e.g., '#ff0000')
    """
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb_to_hex(rgb_str: str) -> Optional[str]:
    """Convert CSS rgb/rgba string to hex color.

    Args:
        rgb_str: CSS color string (rgb(), rgba(), hex, or named color)

    Returns:
        Hex color string or None if invalid
    """
    if not rgb_str:
        return None

    # Handle hex colors (pass through)
    if rgb_str.startswith("#"):
        return rgb_str.lower()

    # Handle rgb(r, g, b) or rgba(r, g, b, a)
    match = re.match(r'rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', rgb_str)
    if match:
        r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"#{r:02x}{g:02x}{b:02x}"

    # Handle named colors (basic set)
    color_names = {
        "black": "#000000",
        "white": "#ffffff",
        "red": "#ff0000",
        "green": "#00ff00",
        "blue": "#0000ff",
        "yellow": "#ffff00",
        "gray": "#808080",
        "grey": "#808080",
        "transparent": None,
    }
    return color_names.get(rgb_str.lower())


def classify_color(hex_color: Optional[str]) -> str:
    """Classify hex color into a semantic category.

    Args:
        hex_color: Hex color string (e.g., '#ff0000')

    Returns:
        Color category: black, white, gray, red, green, blue, yellow, orange, purple, other, unknown
    """
    if not hex_color or not hex_color.startswith("#"):
        return "unknown"

    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except ValueError:
        return "unknown"

    # Grayscale detection
    if abs(r - g) < 20 and abs(g - b) < 20:
        brightness = (r + g + b) / 3
        if brightness < 50:
            return "black"
        elif brightness > 200:
            return "white"
        else:
            return "gray"

    # Color detection based on dominant channel
    max_val = max(r, g, b)
    if r == max_val and r > g + 50 and r > b + 50:
        return "red"
    elif g == max_val and g > r + 50 and g > b + 50:
        return "green"
    elif b == max_val and b > r + 50 and b > g + 50:
        return "blue"
    elif r > 200 and g > 150 and b < 100:
        return "orange"
    elif r > 200 and g > 200 and b < 100:
        return "yellow"
    elif r > 100 and b > 100 and g < 100:
        return "purple"

    return "other"


# Standard category taxonomy across all engines
STANDARD_CATEGORIES = {
    # Primary document structure
    "Title",       # Main headings, section headers
    "Text",        # Body text, paragraphs
    "List-item",   # Bullet points, numbered items

    # Rich content
    "Table",       # Data tables
    "Picture",     # Images, figures, charts
    "Caption",     # Image/table captions

    # Semantic sections
    "Header",      # Page/document headers
    "Footer",      # Page/document footers
    "Footnote",    # Footnotes

    # Code/formulas
    "Code",        # Code blocks, preformatted text
    "Formula",     # Mathematical formulas
}

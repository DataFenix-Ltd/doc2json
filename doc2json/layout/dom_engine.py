"""DOM-based layout detection engine using Playwright."""

import logging
import os
from typing import List

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from .schema import LayoutElement, LayoutStyle
from .utils import rgb_to_hex, classify_color

logger = logging.getLogger(__name__)

# Standard category mapping for HTML tags
TAG_TO_CATEGORY = {
    "h1": "Title",
    "h2": "Title",
    "h3": "Title",
    "h4": "Title",
    "h5": "Title",
    "h6": "Title",
    "p": "Text",
    "div": "Text",
    "span": "Text",
    "li": "List-item",
    "table": "Table",
    "img": "Picture",
    "figure": "Picture",
    "pre": "Code",
    "code": "Code",
    "blockquote": "Text",
    "header": "Header",
    "footer": "Footer",
    "nav": "Text",
    "article": "Text",
    "section": "Text",
}


class DomEngine:
    def __init__(self):
        if sync_playwright is None:
             raise ImportError("playwright is not installed. Please install 'doc2json[layout]'")

    def detect(self, file_path: str) -> List[LayoutElement]:
        """
        Detect layout elements in an HTML file.

        Args:
            file_path: Path to HTML file

        Returns:
            List of LayoutElement with bounding boxes, text content, and styles
        """
        results = []
        absolute_path = os.path.abspath(file_path)
        logger.debug(f"Processing HTML file: {absolute_path}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{absolute_path}")

            # JS script to extract layout elements with full style info
            js_script = """
            () => {
                const tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'table', 'img',
                              'div', 'span', 'li', 'pre', 'code', 'blockquote',
                              'header', 'footer', 'figure', 'article', 'section'];
                let elements = [];
                let id_counter = 1;

                tags.forEach(tag => {
                    document.querySelectorAll(tag).forEach(el => {
                        // Skip invisible elements
                        if (el.offsetParent === null && el.tagName !== 'BODY') return;

                        // Skip elements with no text and no children (unless img)
                        if (el.tagName !== 'IMG' && el.innerText.trim().length === 0) return;

                        // Get Computed Style
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();

                        elements.push({
                            id: id_counter++,
                            tag: el.tagName.toLowerCase(),
                            text_content: el.tagName === 'IMG' ? (el.alt || '') : el.innerText.trim(),
                            bbox: [rect.left, rect.top, rect.right, rect.bottom],
                            style: {
                                font_family: style.fontFamily,
                                font_weight: style.fontWeight,
                                font_style: style.fontStyle,
                                font_size: style.fontSize,
                                color: style.color,
                                background_color: style.backgroundColor,
                                text_align: style.textAlign,
                                text_decoration: style.textDecoration,
                                letter_spacing: style.letterSpacing,
                                line_height: style.lineHeight
                            }
                        });
                    });
                });
                return elements;
            }
            """

            raw_elements = page.evaluate(js_script)
            logger.debug(f"Extracted {len(raw_elements)} raw elements from DOM")

            for raw in raw_elements:
                tag = raw['tag']

                # Map to standard category
                category = TAG_TO_CATEGORY.get(tag, "Text")

                # Normalize BBox
                bbox = [float(x) for x in raw['bbox']]

                # Skip zero-area elements
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    continue

                # Parse style
                s = raw['style']

                # Font category from font family
                f_cat = "unknown"
                font_family_lower = s['font_family'].lower() if s['font_family'] else ""
                if "serif" in font_family_lower and "sans" not in font_family_lower:
                    f_cat = "serif"
                elif "sans" in font_family_lower:
                    f_cat = "sans"
                elif "mono" in font_family_lower or "courier" in font_family_lower:
                    f_cat = "mono"

                # Font weight
                try:
                    weight_val = int(s['font_weight']) if s['font_weight'].isdigit() else 400
                except (ValueError, AttributeError):
                    weight_val = 400
                if "bold" in str(s['font_weight']).lower() or weight_val > 600:
                    weight = "bold"
                elif weight_val < 400:
                    weight = "light"
                else:
                    weight = "normal"

                # Font style (italic)
                font_style_val = s.get('font_style', 'normal')
                font_style = "italic" if "italic" in str(font_style_val).lower() else "normal"

                # Font size
                font_size = None
                if s['font_size'] and 'px' in s['font_size']:
                    try:
                        font_size = float(s['font_size'].replace('px', ''))
                    except ValueError:
                        pass

                # Colors - convert from CSS rgb() to hex
                text_color_hex = rgb_to_hex(s.get('color', ''))
                text_color_class = classify_color(text_color_hex)
                background_hex = rgb_to_hex(s.get('background_color', ''))

                # Text alignment
                alignment = s.get('text_align', 'unknown')
                if alignment not in ["left", "right", "center", "justify"]:
                    alignment = "unknown"

                # Text decoration
                text_decoration = None
                td = s.get('text_decoration', '')
                if td:
                    decorations = []
                    if 'underline' in td:
                        decorations.append('underline')
                    if 'line-through' in td or 'strikethrough' in td:
                        decorations.append('strikethrough')
                    if 'overline' in td:
                        decorations.append('overline')
                    if decorations:
                        text_decoration = decorations

                style_obj = LayoutStyle(
                    font_category=f_cat,
                    typeface_name=s['font_family'].split(',')[0].strip('"\'') if s['font_family'] else None,
                    font_weight=weight,
                    font_style=font_style,
                    font_size=font_size,
                    text_color_hex=text_color_hex,
                    text_color_class=text_color_class,
                    background_color=background_hex,
                    alignment=alignment,
                    text_decoration=text_decoration,
                )

                results.append(LayoutElement(
                    id=raw['id'],
                    category=category,
                    bbox=bbox,
                    text_content=raw['text_content'],
                    style=style_obj
                ))

            browser.close()
            logger.debug(f"Processed {len(results)} layout elements")

        return results

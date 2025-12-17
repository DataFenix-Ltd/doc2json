from PIL import Image, ImageDraw, ImageFont, ImageColor
from typing import List, Tuple, Dict
import os

def draw_som_overlay(image: Image.Image, elements: List[Dict]) -> Image.Image:
    """
    Draws Set-of-Mark (SoM) overlay on the image.
    
    Args:
        image: Original PIL Image.
        elements: List of dicts, each must have 'id' (int) and 'bbox' (list/tuple).
                  bbox format: [x_min, y_min, x_max, y_max].
    
    Returns:
        Annotated PIL Image.
    """
    annotated_img = image.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated_img)
    
    # Try to load a font, fallback to default
    try:
        # Try a standard font that might exist on Mac/Linux
        font = ImageFont.truetype("Arial.ttf", size=12)
    except IOError:
        try:
            # Mac specific
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=14)
        except IOError:
            font = ImageFont.load_default()

    # SoM Settings
    outline_color = "#00FF00" # Neon Green
    outline_width = 2
    text_bg_color = "#000000" # Black background for text
    text_color = "#FFFFFF"    # White text
    
    for el in elements:
        eid = el['id']
        bbox = el['bbox']
        
        # Ensure bbox is valid
        x1, y1, x2, y2 = bbox
        
        # Draw Box
        draw.rectangle([x1, y1, x2, y2], outline=outline_color, width=outline_width)
        
        # Draw Label Tag (Top-Left corner of bbox)
        label = str(eid)
        
        # Calculate label background size
        if hasattr(font, "getbbox"):
            text_bbox = font.getbbox(label)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
        else:
            text_w, text_h = draw.textsize(label, font=font)
            
        pad = 2
        bg_x1, bg_y1 = x1, y1
        bg_x2 = x1 + text_w + (pad * 2)
        bg_y2 = y1 + text_h + (pad * 2)
        
        # Draw Tag Background
        draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=text_bg_color)
        
        # Draw Text
        draw.text((bg_x1 + pad, bg_y1 + pad), label, fill=text_color, font=font)
        
    return annotated_img

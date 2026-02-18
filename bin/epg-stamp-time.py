#!/usr/bin/env python3
"""Stamp current time onto an EPG page PNG in the CHANNEL header cell.

Usage: epg-stamp-time.py <input.png> <output.png>

Renders current time (e.g. "04:35 PM") into the grid header cell at
x=0..220, y=540..580 using the same font/color as the EPG generator.
"""
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TIME_COLOR = (255, 220, 100)
GRID_HEADER_BG = (50, 50, 120)

# Header cell: x=0..220, y=540..580
CELL_X = 0
CELL_Y = 540
CELL_W = 220
CELL_H = 40

def main():
    if len(sys.argv) != 3:
        sys.exit(1)

    src, dst = sys.argv[1], sys.argv[2]
    img = Image.open(src).copy()
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_BOLD_PATH, 24)
    except Exception:
        font = ImageFont.load_default()

    # Clear the cell area
    draw.rectangle([CELL_X, CELL_Y, CELL_X + CELL_W - 1, CELL_Y + CELL_H - 1],
                   fill=GRID_HEADER_BG)

    # Draw current time centered in cell
    now_str = datetime.now().strftime("%I:%M %p")
    bbox = font.getbbox(now_str)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = CELL_X + (CELL_W - tw) // 2
    ty = CELL_Y + (CELL_H - th) // 2
    draw.text((tx, ty), now_str, font=font, fill=TIME_COLOR)

    img.save(dst)

if __name__ == "__main__":
    main()

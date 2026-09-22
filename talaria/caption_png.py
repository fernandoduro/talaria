"""Captions rasterised to PNG (the 'overlay' backend).

The alternative to drawtext for ffmpeg built without libfreetype (e.g. the
minimal Homebrew build on macOS). Each speech segment becomes a frame-sized
RGBA PNG, composited with overlay+enable over the segment's time window —
the same visual result as drawtext.

The style (translucent black box, outlined white text, position) follows the
same config constants drawtext uses, so both routes render alike.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from . import config

_FONT = ImageFont.truetype(config.FONT, config.FONTSIZE)


def _draw_outlined(d, xy, text, fill, ow):
    """Outlined text. Uses Pillow's stroke_width (>=6.2) when available."""
    x, y = xy
    try:
        d.text((x, y), text, font=_FONT, fill=fill, anchor="ls",
               stroke_width=ow, stroke_fill=(0, 0, 0, 255))
    except TypeError:  # old Pillow, no stroke_width
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx * dx + dy * dy <= ow * ow:
                    d.text((x + dx, y + dy), text, font=_FONT,
                           fill=(0, 0, 0, 255), anchor="ls")
        d.text((x, y), text, font=_FONT, fill=fill, anchor="ls")


def render_caption_png(lines: list[str], out_path: str) -> str:
    """Draws a caption's lines into a transparent 1080x1920 PNG.

    Mirrors the drawtext layout: centred lines stacked upwards from BASE_Y,
    each over a translucent black box.
    """
    img = Image.new("RGBA", (config.FRAME_W, config.FRAME_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(lines)
    alpha = int(round(config.CAP_BOX_ALPHA * 255))
    pad = config.CAP_BOX_BORDER

    for li, line in enumerate(lines):
        y = config.BASE_Y - (n - 1 - li) * config.LINE_H
        w = _FONT.getlength(line)
        x = (config.FRAME_W - w) / 2
        # box behind the text (equivalent to box=1:boxcolor=black@ALPHA)
        asc, desc = _FONT.getmetrics()
        d.rectangle([x - pad, y - asc - pad, x + w + pad, y + desc + pad],
                    fill=(0, 0, 0, alpha))
        _draw_outlined(d, (x, y), line, (255, 255, 255, 255), config.CAP_BORDER)

    img.save(out_path)
    return out_path


def build_overlay_graph(caption_items, base_label="comp", out_label="outv") -> str:
    """Builds the overlay chain from [(png_path, start, end)].

    The PNGs enter as extra ffmpeg inputs (indices 1..N, since 0 is the video).
    Returns the filtergraph fragment that chains the overlays.
    """
    if not caption_items:
        return f"[{base_label}]null[{out_label}]"

    parts, cur = [], base_label
    for i, (_png, rs, re_) in enumerate(caption_items, start=1):
        nxt = out_label if i == len(caption_items) else f"ov{i}"
        parts.append(
            f"[{cur}][{i}:v]overlay=0:0:enable='between(t,{rs:.3f},{re_:.3f})'[{nxt}]"
        )
        cur = nxt
    return ";".join(parts)

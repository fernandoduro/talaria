"""End card: logo + @handle at the end of every clip, with a fade-in.

The card is static — identical in every clip, independent of the video content.
Building it inside each render's filtergraph would mean remaking the same PNG
for every clip; instead it is composed once with Pillow and cached as a silent
`.mp4` in the pipeline's codec/resolution, which `render_cut` concatenates with
the concat filter — the reason for that is in `render.append_end_card`.
"""
from __future__ import annotations

import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from . import config, layout

_HANDLE_SIZE = 50


def compose_card() -> Image.Image:
    """The card's static frame: solid background, logo + @handle centred.

    Returns the image in memory — the caller decides whether to write a PNG, a
    video, or only inspect it (which is what the tests do, without needing the
    cached ffmpeg run).
    """
    if not os.path.exists(config.LOGO_PATH):
        raise FileNotFoundError(
            f"end-card logo not found at {config.LOGO_PATH} — "
            f"the file should be versioned under assets/"
        )

    frame = Image.new("RGB", (config.FRAME_W, config.FRAME_H), config.CARD_BG)

    logo = Image.open(config.LOGO_PATH).convert("RGBA")
    logo_w = config.CARD_LOGO_W
    logo_h = int(logo.height * logo_w / logo.width)
    logo_r = logo.resize((logo_w, logo_h))

    fonte = ImageFont.truetype(config.FONT, _HANDLE_SIZE)
    d = ImageDraw.Draw(frame)
    bbox = d.textbbox((0, 0), config.CARD_HANDLE, font=fonte)
    handle_h = bbox[3] - bbox[1]

    # The logo + gap + @handle block is centred as one unit, not each piece
    # centred on its own — otherwise the distance between them varies with the
    # system font size.
    space = 40
    block_h = logo_h + space + handle_h
    top = (config.FRAME_H - block_h) // 2

    frame.paste(logo_r, ((config.FRAME_W - logo_w) // 2, top), logo_r)
    d.text(((config.FRAME_W - (bbox[2] - bbox[0])) // 2, top + logo_h + space),
           config.CARD_HANDLE, font=fonte, fill=config.CARD_HANDLE_COLOR)

    return frame


def cached_card(project_dir: str) -> str:
    """Path of the card as video, generating (or regenerating) when needed.

    Cached on the logo's mtime: if `LOGO_PATH` is newer than the card already
    written, it regenerates. Replacing the logo file (a redesign) is enough —
    nothing has to be deleted by hand.
    """
    destination = layout.ensure_dir(layout.end_card_mp4(project_dir))
    exists = os.path.exists(destination)
    if exists and os.path.getmtime(destination) >= os.path.getmtime(config.LOGO_PATH):
        return destination

    # Writes to a temporary file of this process alone and only swaps it for
    # the final name with os.replace (atomic on the same filesystem) — the same
    # pattern as published.json. Without it, two concurrent `render` runs on the
    # same episode (common: one terminal per clip) would write to the same
    # `frame_path`/`destination` and one would corrupt the other's card
    # mid-ffmpeg, with no visible error.
    # ffmpeg picks the output format from the extension — it has to end in
    # .mp4/.png, not in some arbitrary suffix after them.
    stem = destination[:-4] if destination.endswith(".mp4") else destination
    tmp_dest = f"{stem}.{os.getpid()}.tmp.mp4"
    frame_path = f"{stem}.{os.getpid()}.tmp.png"
    compose_card().save(frame_path)
    try:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-loop", "1", "-t", str(config.CARD_DURATION_S), "-i", frame_path,
            "-f", "lavfi", "-t", str(config.CARD_DURATION_S),
            "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", f"fade=in:st=0:d={config.CARD_FADE_S},format={config.PIX_FMT}",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            "-shortest", tmp_dest,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to build the card:\n{r.stderr[-1500:]}")
        os.replace(tmp_dest, destination)
    finally:
        if os.path.exists(frame_path):
            os.remove(frame_path)
        if os.path.exists(tmp_dest):
            os.remove(tmp_dest)

    return destination

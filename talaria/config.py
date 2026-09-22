"""Central pipeline configuration.

Every render/thumbnail/transcription constant lives here — no absolute paths
and no episode-specific text scattered through the code.
"""
import os
import shutil

# ---------------------------------------------------------------------------
# Fonts — versioned under assets/fonts/.
#
# Text is burned into the video and rasterised into the PNGs, so the font
# decides the published result. fc-match substitutes silently: ask for Poppins
# and get Noto Sans, and the layout comes out wrong with no error. A file in the
# repository = same render on any machine, and a missing file aborts at import.
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTS_DIR = os.path.join(_ROOT, "assets", "fonts")


def _bundled_font(name: str) -> str:
    path = os.path.join(_FONTS_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"font {name} not found in assets/fonts — the file is "
            f"versioned; restore it with 'git checkout assets/fonts/{name}'."
        )
    return path


FONT = _bundled_font("DejaVuSans-Bold.ttf")

# ---------------------------------------------------------------------------
# Caption backend — detected at runtime.
#
# 'drawtext' is the default path, but it needs ffmpeg built with
# libfreetype. Minimal builds (e.g. Homebrew on macOS) lack the filter; in that
# case we fall back to 'overlay': captions rasterised to PNG with Pillow and
# composited with overlay+enable. Same visual result, with no dependency on
# ffmpeg's external libs.
# ---------------------------------------------------------------------------
def has_drawtext() -> bool:
    """True if this environment's ffmpeg has the drawtext filter."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return False
    import subprocess
    try:
        out = subprocess.run([ff, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return False
    return any(line.split()[1:2] == ["drawtext"] for line in out.splitlines() if line.strip())


# 'drawtext' | 'overlay' — override with TALARIA_CAPTION_BACKEND to force one.
CAPTION_BACKEND = os.environ.get(
    "TALARIA_CAPTION_BACKEND",
    "drawtext" if has_drawtext() else "overlay",
)

# ---------------------------------------------------------------------------
# Vertical video (Shorts / Reels)
# ---------------------------------------------------------------------------
FRAME_W = 1080
FRAME_H = 1920

# Caption (drawtext) — libass does not draw reliably in this environment.
FONTSIZE = 40
SAFE_W = 980            # max line width in px (leaves ~50px of margin per side)
LINE_H = 58             # vertical spacing between lines
# y of the LAST line's baseline. Lines stack upwards, so this value has to
# leave room below the video band for the tallest caption: with a 1280x720
# source scaled to FG_SCALE_W the band ends at y=1340 and 580px of blur remain.
# At 1360 a 5-line caption climbed to y=1128 and invaded the video; at 1560 it
# starts at 1328 and stays entirely inside the blur.
BASE_Y = 1560
CAP_BORDER = 4          # text outline
CAP_BOX_ALPHA = 0.55    # opacity of the box behind the text
CAP_BOX_BORDER = 12     # box padding

# 9:16 framing over a blurred background
BG_BLUR_SIGMA = 28      # background blur
FG_SCALE_W = 1350       # foreground video width (people with good presence)

# Encode
VCODEC = "libx264"
PRESET = "medium"
CRF = "20"
PIX_FMT = "yuv420p"
ACODEC = "aac"
ABITRATE = "160k"

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
WHISPER_MODEL = "small"   # safe for 4GB GPUs; 'medium' blew up a GTX 1650
WHISPER_LANG = "en"

# Grouping words -> sentences (VTT and Whisper parsers)
SEG_MAX_GAP = 0.7         # pause (s) that breaks the sentence
SEG_MAX_DUR = 5.0         # max duration (s) of a segment
SEG_MAX_CHARS = 75        # max characters before breaking
SEG_END_PAD = 0.4         # padding at the end of each segment (s)

# ---------------------------------------------------------------------------
# Curation
# ---------------------------------------------------------------------------
CLIP_MIN_S = 60         # minimum clip duration
CLIP_MAX_S = 90         # maximum duration
GUEST_SPEECH_MIN = 0.5 # minimum fraction of guest speech in the clip

# ---------------------------------------------------------------------------
# Thumbnail (YouTube)
# ---------------------------------------------------------------------------
THUMB_W = 1280
THUMB_H = 720
THUMB_ORANGE = (240, 100, 20)
THUMB_WHITE = (255, 255, 255)
THUMB_BRIGHTNESS = 0.82
THUMB_CONTRAST = 1.08

# ---------------------------------------------------------------------------
# Instagram quote post (4:5)
#
# The measurements come from the template itself
# (assets/template_instagram.png), measured pixel by pixel. The placeholder
# carries gradient, rule and bar; logo and quote marks are the channel's. The
# code writes quote, name and role on top.
# ---------------------------------------------------------------------------
POST_TEMPLATE = os.path.join(_ROOT, "assets", "template_instagram.png")

# ---------------------------------------------------------------------------
# Watermark and end card
# ---------------------------------------------------------------------------
LOGO_PATH = os.path.join(_ROOT, "assets", "logo.png")
WATERMARK_W = 170
WATERMARK_MARGIN = 40
CARD_DURATION_S = 3.5
CARD_FADE_S = 0.35
CARD_LOGO_W = 620
CARD_HANDLE = "@yourhandle"
CARD_HANDLE_COLOR = (255, 140, 66)   # orange
CARD_BG = (10, 10, 10)

POST_W = 2160
POST_H = 2700

POST_MARGIN_X = 195       # left margin for all text
POST_TEXT_W = 1800  # max width of a quote line

# Quote. Lines stack DOWNWARDS from POST_QUOTE_Y, inherited from the original
# layout: the placeholder draws nothing at that height to check against.
POST_QUOTE_Y = 1144
POST_QUOTE_STEP = 190      # distance between consecutive line starts
POST_QUOTE_LINE_H = 160     # height of one text line
POST_QUOTE_MAX_LINES = 5   # a 6th would invade the rule at y=2242
POST_RULE_Y = 2242

# Footer (the rule already comes drawn on the template)
# Show name, used in the thumbnail badge. Changing it here applies to every
# episode — it is channel identity, not per-episode data.
SHOW_NAME = "MY PODCAST"

POST_NAME_Y = 2338
POST_ROLE_Y = 2459

# 150 and not 160: Poppins is wider than the Avenir Next Demi Bold the layout
# was measured in, and at 160 the reference quote becomes 6 lines — the 6th
# would cross the rule at y=2242. At 150 the fullest line has 83px to spare.
POST_QUOTE_SIZE = 150
POST_NAME_SIZE = 62
POST_ROLE_SIZE = 38

POST_QUOTE_COLOR = (245, 242, 234)
POST_NAME_COLOR = (255, 255, 255)
POST_ROLE_COLOR = (154, 149, 144)

# Font for the post's quote and footer.
POST_FONT = _bundled_font("Poppins-SemiBold.ttf")
POST_MONO = _bundled_font("DejaVuSansMono-Bold.ttf")

# ---------------------------------------------------------------------------
# Scheduled publishing
# ---------------------------------------------------------------------------
# Publishing timezone — explicit because a machine on UTC near midnight would
# silently shift the publication day — dates always carry a zone.
PUBLISH_TZ = "America/Sao_Paulo"

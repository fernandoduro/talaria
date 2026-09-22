"""Renders vertical 9:16 clips (blurred background) with burned-in captions.

The caption backend (drawtext or a PNG overlay) is chosen at runtime by
config.CAPTION_BACKEND — see talaria/caption_png.py.

Reads transcript.json (segments) + moments.json (curated clips) and, per clip,
produces the vertical MP4 with captions for the chosen platforms.

moments.json: a list of {slug, start, end, ...}. Extra fields (who, title,
screen_text) are ignored here — they serve the texts.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from PIL import ImageFont

from . import (audio, caption, caption_png, config, end_card, episode,
               layout, texts, utils)

_PILFONT = ImageFont.truetype(config.FONT, config.FONTSIZE)


def _text_width_px(s: str, fnt=None) -> float:
    return (fnt or _PILFONT).getlength(s)


def wrap_by_pixels(txt: str, fnt=None, width: float | None = None) -> list[str]:
    """Wraps text by REAL PIXEL WIDTH (not by character count).

    Guarantees no line exceeds the width. Uses as many lines as it needs —
    3 short lines beat text cut off at the edges.

    With no arguments it wraps the video's burned-in caption (font and SAFE_W
    from config). With `fnt`/`width` it also serves the quote post, which has a
    different font and area.
    """
    width = config.SAFE_W if width is None else width
    words = txt.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip() if cur else w
        if _text_width_px(cand, fnt) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _esc_drawtext(s: str) -> str:
    """Escapes text for the text= value inside -filter_complex."""
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:").replace("'", "’")
    s = s.replace("%", "\\%").replace(",", "\\,")
    return s


def _drawtext_chain(segments, start, end, names=None) -> str:
    """Builds the drawtext filter chain for a clip's captions."""
    parts = []
    # Same source of truth as the overlay backend: without it drawtext lost the
    # text trimming and showed speech the clip does not play.
    for rs, re_, txt in _segments_in_cut(segments, start, end, names):
        lines = wrap_by_pixels(txt)
        n = len(lines)
        for li, line in enumerate(lines):
            y = config.BASE_Y - (n - 1 - li) * config.LINE_H
            t = _esc_drawtext(line)
            parts.append(
                f"drawtext=fontfile='{config.FONT}':text='{t}':"
                f"fontsize={config.FONTSIZE}:fontcolor=white:"
                f"borderw={config.CAP_BORDER}:bordercolor=black:"
                f"box=1:boxcolor=black@{config.CAP_BOX_ALPHA}:"
                f"boxborderw={config.CAP_BOX_BORDER}:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{rs:.3f},{re_:.3f})'"
            )
    return ",".join(parts) if parts else "null"


def _filtergraph(segments, start, end, names=None) -> str:
    """9:16 over a blurred background + captions via drawtext."""
    draw = _drawtext_chain(segments, start, end, names)
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={config.FRAME_W}:{config.FRAME_H}:force_original_aspect_ratio=increase,"
        f"crop={config.FRAME_W}:{config.FRAME_H},gblur=sigma={config.BG_BLUR_SIGMA}[bgb];"
        f"[fg]scale={config.FG_SCALE_W}:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{draw}[outv]"
    )


def _watermark_graph(in_label: str, logo_label: str) -> str:
    """Logo overlay in the top-right corner, chained after the caption.

    Both caption backends (`drawtext` and `overlay`) already converge on the
    `[outv]` label — the watermark goes in after that, producing `[outv2]`,
    without touching `_filtergraph` or `caption_png.build_overlay_graph`.
    """
    return (
        f"[{logo_label}]scale={config.WATERMARK_W}:-1[wm];"
        f"[{in_label}][wm]overlay=W-w-{config.WATERMARK_MARGIN}:"
        f"{config.WATERMARK_MARGIN}[outv2]"
    )


BASE_GRAPH = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
    "crop={W}:{H},gblur=sigma={S}[bgb];"
    "[fg]scale={FW}:-2[fgs];"
    "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp]"
)


def _base_graph() -> str:
    return BASE_GRAPH.format(W=config.FRAME_W, H=config.FRAME_H,
                             S=config.BG_BLUR_SIGMA, FW=config.FG_SCALE_W)


def _segments_in_cut(segments, start, end, names=None):
    """Segments appearing in the clip, with times relative to its start.

    When the clip trims a segment (starting or ending mid-way through it), the
    TEXT is trimmed in the same proportion. Without that the caption shows
    speech the clip's audio never reaches: the last segment sat 1.4s on screen
    displaying the whole block's 150 characters, while the audio only said the
    first 4 words.
    """
    out = []
    for seg in segments:
        s, e = seg["start"], seg["end"]
        if e <= start or s >= end:
            continue
        txt = utils.fix_proper_nouns(utils.clean_caption(seg["text"]), names)
        if not txt:
            continue
        vis_s, vis_e = max(s, start), min(e, end)
        if (vis_e - vis_s) < CAPTION_MIN_S:
            continue          # too fast to read: it only blinks on screen
        txt = _trim_text(txt, (vis_s - s) / (e - s), (vis_e - s) / (e - s))
        if not txt:
            continue
        out.append((vis_s - start, vis_e - start, txt))
    return out


# Minimum screen time for a caption to be worth it. The clip end comes from the
# audio valley, not the transcript grid, so milliseconds of the next block are
# left over — without this floor they became 1-frame PNGs ("Few" blinking at
# the clip end, the very word the audio adjustment had removed).
CAPTION_MIN_S = 0.30


# Minimum slack taken off the clip end, to absorb rounding when the audio
# adjustment does not run (no ffmpeg, or the end already in the valley).
END_MARGIN_S = 0.02

# How far the audio adjustment may back off. Beyond that the clip would lose
# content instead of gaining cleanliness, and the problem is the chosen end.
AUDIO_ADJUST_MAX_S = 0.5


def apply_end_margin(end: float, start: float) -> float:
    """Pulls the clip end back by the margin, respecting the minimum duration.

    A clip already at the 60s limit cannot shrink: the margin exists to absorb
    rounding, not to break the duration rule.
    """
    floor = start + min(config.CLIP_MIN_S, end - start)
    return max(floor, end - END_MARGIN_S)


def adjust_end_by_audio(video_path, start, end):
    """Moves the clip end to the nearest pause in speech.

    The times come from the transcript, whose resolution is 1 second — the end
    lands on the boundary between two words and leaks the attack of the next
    ("Few"). This is the correction that used to be made by measuring the
    envelope by hand.

    Backs off at most AUDIO_ADJUST_MAX_S and never below the minimum duration;
    with no ffmpeg it falls back to the fixed margin.
    """
    valley = audio.valley_before(video_path, end, search=AUDIO_ADJUST_MAX_S)
    if valley >= end or (end - valley) > AUDIO_ADJUST_MAX_S:
        return apply_end_margin(end, start)
    if (valley - start) < config.CLIP_MIN_S:
        return apply_end_margin(end, start)
    return valley


def _trim_text(txt: str, start: float, end: float) -> str:
    """Cuts `txt` to the proportional slice [start, end] (0..1), by word.

    The transcript carries no per-word time, so the position is estimated
    proportionally to the text — close enough not to display a sentence the clip
    does not play. The cut is made on a word boundary: cutting by character
    would leave "reprodu" on screen (half of "reproduce").
    """
    if start <= 0 and end >= 1:
        return txt
    words = txt.split()
    if not words:
        return txt
    n = len(words)
    a = max(0, min(n, int(round(start * n))))
    b = max(a, min(n, int(round(end * n))))
    if b - a < 1:                     # slice too short: keep 1 word
        b = min(n, a + 1)
    # The proportional estimate is off by a word or two. In both directions the
    # target is the same: close the caption at the punctuation nearest the clip,
    # instead of leaving it hanging mid-sentence.
    if b < n:
        b = _snap_to_punctuation(words, b)
    return " ".join(words[a:b])


# How many words the adjustment may travel to find punctuation. Two in each
# direction covers the typical error of the proportional estimate without
# letting the caption invade the next sentence.
PUNCTUATION_WINDOW = 2


def _snap_to_punctuation(words: list, b: int) -> int:
    """Moves the slice end to the nearest punctuation, within the window.

    Going back avoids dragging in the start of the next sentence ("...reproduce
    it. I think"); going forward avoids cutting before the full stop the audio
    has already reached ("a lot more of the" when the speech says "a lot more
    of the same.").
    """
    sentence_end = (".", "!", "?", "…")
    for d in range(0, PUNCTUATION_WINDOW + 1):
        behind = b - 1 - d
        if behind >= 0 and words[behind].endswith(sentence_end):
            return behind + 1
        ahead = b - 1 + d
        if ahead < len(words) and words[ahead].endswith(sentence_end):
            return ahead + 1
    return b


def _build_overlay_inputs(segments, start, end, tmpdir, names=None):
    """Rasterises one PNG per segment. Returns [(png, rel_start, rel_end)]."""
    items = []
    for i, (rs, re_, txt) in enumerate(_segments_in_cut(segments, start, end, names)):
        png = os.path.join(tmpdir, f"cap_{i:05d}.png")
        caption_png.render_caption_png(wrap_by_pixels(txt), png)
        items.append((png, rs, re_))
    return items


def append_end_card(clip_path: str, project_dir: str) -> None:
    """Appends the end card to the end of `clip_path`, in place.

    Uses the CONCAT FILTER, not the concat demuxer with `-c copy`. Tried in
    practice: `-c copy` produced a file almost the size of the clip alone,
    because the two pieces come from independent encodes (the clip from the main
    filtergraph, the card from Pillow) with timestamps that do not chain — ffmpeg
    warns "Non-monotonic DTS" and the card ends up discarded or truncated, with
    NO error return. The concat filter re-encodes this step (short — only the
    join, not the whole clip) and recomputes the timestamps from zero with
    `setpts`/`asetpts`, which fixes it.
    """
    card_path = end_card.cached_card(project_dir)

    tmpdir = tempfile.mkdtemp(prefix="talaria_concat_")
    try:
        concat_path = os.path.join(tmpdir, "concatenated.mp4")
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", clip_path, "-i", card_path,
            "-filter_complex",
            # setsar=1 normalises the pixel aspect ratio: the card (made from
            # the static PNG) and the clip (from the main filtergraph) can come
            # out with different SAR even at the same pixel resolution, and the
            # concat filter — unlike the demuxer — rejects inputs whose video
            # parameters do not match exactly.
            "[0:v]setpts=PTS-STARTPTS,setsar=1[v0];[0:a]asetpts=PTS-STARTPTS[a0];"
            "[1:v]setpts=PTS-STARTPTS,setsar=1[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            concat_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to concatenate the end card:\n"
                               f"{r.stderr[-1500:]}")
        shutil.move(concat_path, clip_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def render_cut(video_path, segments, moment, project_dir, platforms, names=None):
    """Renders one clip for the chosen platforms (youtube/instagram)."""
    slug = moment["slug"]
    start, end = float(moment["start"]), float(moment["end"])
    end = adjust_end_by_audio(video_path, start, end)

    outputs = []
    if "youtube" in platforms:
        outputs.append(("youtube_shorts", f"{slug}_short.mp4"))
    if "instagram" in platforms:
        outputs.append(("instagram_reels", f"{slug}_reel.mp4"))

    if not outputs:
        raise ValueError("No platform selected (use youtube and/or instagram).")

    # Render once; if both platforms were asked for, copy (pixel-identical).
    first_subdir, first_name = outputs[0]
    first_dir = layout.platform(project_dir, first_subdir)
    os.makedirs(first_dir, exist_ok=True)
    first_out = os.path.join(first_dir, first_name)

    print(f"[render] {slug} ({end - start:.0f}s) -> {first_subdir}/{first_name} "
          f"[caption: {config.CAPTION_BACKEND}]")

    tmpdir = None
    try:
        if config.CAPTION_BACKEND == "drawtext":
            seek_inputs = ["-i", video_path]
            fg = _filtergraph(segments, start, end, names)
        else:
            # Rasterise the captions to PNG and composite with overlay+enable.
            tmpdir = tempfile.mkdtemp(prefix=f"talaria_{slug}_")
            items = _build_overlay_inputs(segments, start, end, tmpdir, names)
            seek_inputs = ["-i", video_path]
            for png, _rs, _re in items:
                seek_inputs += ["-i", png]
            fg = _base_graph() + ";" + caption_png.build_overlay_graph(items)

        # The watermark enters as the LAST input, with `-loop 1` — without the
        # loop a static image is a single frame at t=0, and inheriting the
        # video's `-ss`/`-to` would produce an empty stream (measured: ffmpeg
        # trims BEFORE that frame and nothing is left). With `-loop 1` the
        # stream is continuous and the preceding -ss/-to does not affect it.
        logo_idx = len(seek_inputs) // 2   # each seek_inputs item is "-i, path"
        fg += ";" + _watermark_graph("outv", str(logo_idx))

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-to", str(end), *seek_inputs,
            "-loop", "1", "-i", config.LOGO_PATH,
            "-filter_complex", fg,
            "-map", "[outv2]", "-map", "0:a",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            "-movflags", "+faststart",
            "-shortest",
            first_out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed on {slug}:\n{r.stderr[-1500:]}")
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # The tail check runs BEFORE concatenating the card, not after: it measures
    # the audio energy exactly at instant `end - start` inside the file,
    # expecting to find there the end (silent or not) of the real speech. Once
    # concatenated, that same instant becomes where the SILENT card begins — the
    # reading would always see a drop in energy there (speech -> card silence)
    # and report "clean tail" even when the speech was cut mid-word. The order
    # matters: measure on the file without the card.
    if audio.clips_mid_word(first_out, end - start):
        print(f"[render] !! {slug}: the speech does not end cleanly — the end "
              f"may be cutting a word. Adjust `end` and render again.")

    # The card goes in AFTER the check above and BEFORE copying to the other
    # platforms — both platforms need the same final file.
    append_end_card(first_out, project_dir)

    for subdir, name in outputs[1:]:
        d = layout.platform(project_dir, subdir)
        os.makedirs(d, exist_ok=True)
        shutil.copy2(first_out, os.path.join(d, name))

    # Publishing caption beside each piece: the manager opens it and pastes into
    # the caption field. Written after the copies so every platform is covered.
    write_captions(project_dir, moment,
                     [os.path.join(layout.platform(project_dir, sub), name)
                      for sub, name in outputs])

    print(f"[render] {slug} OK")


def _is_youtube_output(piece: str) -> bool:
    """True when the piece is in the YouTube output folder.

    The folder is what distinguishes the two copies: the mp4 is pixel-identical
    and the slug is the same, only the directory changes. It comes from
    `layout`, never from a literal.
    """
    folder = os.path.basename(os.path.dirname(os.path.abspath(piece)))
    return folder == layout.YOUTUBE_SHORTS


def write_captions(project_dir, moment, pieces):
    """Writes the publishing caption beside each rendered piece.

    The description is the `post_caption` curation wrote for the clip; the
    hashtags apply to the whole episode and come from `texts.json`.

    The call to the full episode goes ONLY into the YouTube `.txt`: on Instagram
    the URL is not clickable and sends the reader out of the app. That is the one
    reason the two pieces stop having identical captions.

    A clip with no `post_caption` still gets the file (the hashtags already save
    work), but it WARNS: a published mute caption is worse than a missing one,
    because it goes unnoticed until it is live.
    """
    caption.validate("post_caption", moment.get("post_caption"), moment["slug"])
    description = (moment.get("post_caption") or "").strip()
    if not description:
        print(f"[caption] !! {moment['slug']}: no post_caption — the .txt "
              f"comes out with the hashtags only. Fill it in "
              f"decisions/curation.json.")

    hashtags = (texts.load(project_dir) or {}).get("hashtags", "")
    url = episode.youtube_url(project_dir)
    if not url:
        print(f"[caption] !! {moment['slug']}: no youtube_url in "
              f"episode.json — the Short goes out with no call to the full "
              f"episode. Fill it when the long video is live.")

    written = []
    for piece in pieces:
        text = caption.compose(description, hashtags,
                              url if _is_youtube_output(piece) else None)
        written.append(caption.write(piece, text))
    return written


def write_episode_caption(project_dir):
    """Writes the episode title + description to `publish/episode.txt`.

    `texts.json` is JSON, so copying the description from there into YouTube
    means dealing with escaped `\\n`. This file is the same content already
    formatted, to open and paste.

    Returns `None` without creating a file when there are no texts yet: an
    episode before the materials step has nothing to paste, and an empty `.txt`
    in the publishing folder would only confuse.
    """
    data = texts.load(project_dir) or {}
    text = caption.compose_episode(data.get("title"), data.get("description"),
                                   data.get("hashtags"))
    if not text:
        return None
    destination = layout.ensure_dir(layout.episode_txt(project_dir))
    with open(destination, "w", encoding="utf-8") as f:
        f.write(text)
    return destination


def render_all(project_dir, platforms, only=None):
    """Renders every clip in moments.json (or only the slugs in `only`)."""
    video_path = layout.video(project_dir)
    with open(layout.transcript(project_dir), encoding="utf-8") as f:
        segments = json.load(f)["segments"]
    with open(layout.moments(project_dir), encoding="utf-8") as f:
        moments = json.load(f)

    names = _proper_nouns(project_dir)

    for m in moments:
        if only and m["slug"] not in only:
            continue
        render_cut(video_path, segments, m, project_dir, platforms, names=names)

    # Episode title and description come out with it: whoever renders is
    # publishing, and that is when both texts get pasted into YouTube.
    ep_txt = write_episode_caption(project_dir)
    if ep_txt:
        print(f"[caption] episode -> {os.path.basename(ep_txt)}")


def _proper_nouns(project_dir):
    """Names the caption must spell the way episode.json dictates.

    Transcription gets proper nouns wrong (Zarvik/Zarvic/Zlarvik) and the caption
    is burned into the video. An episode with no metadata does not break the
    render — it goes on without the correction.
    """
    try:
        ep = episode.load(project_dir)
    except (FileNotFoundError, ValueError):
        return []
    names = [ep.get("company", "")]
    names += [c.get("name", "") for c in ep.get("guests") or []]
    return [n for n in names if n and len(n) >= 4]

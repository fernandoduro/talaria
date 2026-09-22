"""Obtains the source video from a local file, a YouTube link or a Drive link.

Always saves to <project>/source/video.mp4 (see layout.video) and returns the path.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

from . import layout

YT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)
DRIVE_RE = re.compile(r"drive\.google\.com", re.IGNORECASE)


def detect_source(src: str) -> str:
    """Classifies the source: 'youtube', 'drive' or 'local'."""
    if YT_RE.search(src):
        return "youtube"
    if DRIVE_RE.search(src):
        return "drive"
    return "local"


def youtube_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _ytdlp(args, capture=False):
    ytdlp = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")
    cmd = [ytdlp, *args]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True)
    return subprocess.run(cmd, check=True)


def acquire(src: str, project_dir: str) -> str:
    """Downloads/copies the video to layout.video(project_dir), returns the path."""
    dest = layout.ensure_dir(layout.video(project_dir))
    kind = detect_source(src)

    if kind == "local":
        if not os.path.exists(src):
            raise FileNotFoundError(f"Arquivo não encontrado: {src}")
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
        print(f"[acquire] local -> {dest}")
        return dest

    # youtube or drive: download the best mp4 available
    print(f"[acquire] baixando ({kind}) com yt-dlp...")
    r = _ytdlp([
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", dest, src,
    ], capture=True)
    if r.returncode != 0 or not os.path.exists(dest):
        raise RuntimeError(f"yt-dlp falhou ao baixar:\n{r.stderr[-1500:]}")
    print(f"[acquire] {kind} -> {dest}")
    return dest


def fetch_youtube_captions(url: str, project_dir: str, lang="pt") -> str | None:
    """Tries to download YouTube's automatic captions (VTT). Returns the .vtt
    path, or None when there are none. Far faster than transcribing."""
    vid = youtube_id(url)
    if not vid:
        return None
    folder = layout.source_dir(project_dir)
    os.makedirs(folder, exist_ok=True)
    out_tpl = os.path.join(folder, "yt_%(id)s.%(ext)s")
    print(f"[acquire] tentando legenda automática ({lang}) do YouTube...")
    _ytdlp([
        "--skip-download", "--write-auto-subs", "--sub-langs", lang,
        "--sub-format", "vtt", "-o", out_tpl, url,
    ], capture=True)
    vtt = os.path.join(folder, f"yt_{vid}.{lang}.vtt")
    if os.path.exists(vtt) and os.path.getsize(vtt) > 0:
        print(f"[acquire] legenda encontrada -> {vtt}")
        return vtt
    print("[acquire] sem legenda automática disponível.")
    return None

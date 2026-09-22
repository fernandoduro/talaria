"""A correct parser for YouTube's rolling VTT.

Each cue has 2 text lines: the consolidated one (repetition, no tags) and the
new one (<c> per-word timing tags). We use ONLY the <c> line: no duplication.
"""
from __future__ import annotations

from . import utils


def parse_vtt(path: str) -> list[dict]:
    """Reads the VTT and returns segments [{start, end, text}]."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    words = []  # (time, word)
    i = 0
    while i < len(lines):
        m = utils.RE_CUE.match(lines[i])
        if not m:
            i += 1
            continue
        cue_start = utils.vtt_ts_to_sec(m.group(1))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() != "" and not utils.RE_CUE.match(lines[i]):
            buf.append(lines[i])
            i += 1
        # the "new" line is the one carrying <c> tags
        newline = next((l for l in buf if "<c>" in l), None)
        if newline is None:
            continue
        # text before the first inline tag belongs to the cue start
        import re
        head = re.sub(r"<[^>]+>", "", utils.RE_INLINE.split(newline)[0]).strip()
        if head:
            for w in head.split():
                words.append((cue_start, w))
        for ts, txt in utils.RE_INLINE.findall(newline):
            t = utils.vtt_ts_to_sec(ts)
            for w in re.sub(r"<[^>]+>", "", txt).strip().split():
                words.append((t, w))

    return utils.group_words_into_segments(words)

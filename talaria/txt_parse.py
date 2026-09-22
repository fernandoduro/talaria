"""Parser for a timestamped .txt transcript (YouTube "copy transcript" format).

Expected format — a timestamp alone on a line, text on the lines after it:

    0:10
    Hey everyone, today we are recording here in Fairbrook...
    0:15
    We are going to talk a bit about Zarvik and how it got here...

The ">>" marker means the speaker changed and is kept as a flag on the segment
(turn=True), useful in curation: a clip starting on a turn change tends to have
a natural boundary.

Careful: ">>" says THAT the speaker changed, not WHO started talking. So the
identity is resolved once, over the whole episode (resolve_speakers), and
recorded on each segment as speaker="host" or "guest". Deducing the speaker
inside one clip's slice does not work: a clip starting mid-answer has no ">>"
to orient itself by.

Output: [{start, end, text, turn, speaker}]. The first three fields are
identical to vtt_parse/whisper, so the rest of the pipeline cannot tell the
origin apart; `speaker` is exclusive to this origin, because only the YouTube
transcript carries the turn marker.
"""
from __future__ import annotations

import re

from . import utils

# "0:10", "10:00", "1:02:03" — alone on the line
RE_TS_LINE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _ts_to_sec(m: re.Match) -> float:
    a, b, c = m.group(1), m.group(2), m.group(3)
    if c is None:            # M:SS  -> minute:second
        return int(a) * 60 + int(b)
    return int(a) * 3600 + int(b) * 60 + int(c)   # H:MM:SS


def parse_txt(path: str, total_duration: float | None = None) -> list:
    """Reads the .txt and returns segments [{start, end, text, turn, speaker}].

    Each block's end is the next block's start (the transcript marks no end).
    The last block uses total_duration when given; otherwise it estimates from
    the speaking rate (145 words per minute).
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    blocks = []   # (start, [text lines])
    cur_start, buf = None, []
    for raw in lines:
        line = raw.strip()
        m = RE_TS_LINE.match(line)
        if m:
            if cur_start is not None:
                blocks.append((cur_start, buf))
            cur_start, buf = _ts_to_sec(m), []
        elif line and cur_start is not None:
            buf.append(line)
    if cur_start is not None:
        blocks.append((cur_start, buf))

    raw = []
    for i, (start, buf) in enumerate(blocks):
        text = " ".join(buf).strip()
        if not text:
            continue
        turn = text.startswith(">>")
        text = utils.strip_markup(text.lstrip("> ").strip())
        if not text:
            continue
        if i + 1 < len(blocks):
            end = float(blocks[i + 1][0])
        elif total_duration:
            end = float(total_duration)
        else:
            end = start + max(1.0, len(text.split()) / 145 * 60)
        raw.append({"start": float(start), "end": round(end, 3),
                    "text": text, "turn": turn})
    return resolve_speakers(regroup_into_sentences(raw))


def regroup_into_sentences(blocks: list) -> list:
    """Regroups ~5s blocks into SENTENCE segments.

    The YouTube transcript breaks every ~5s, mid-sentence ("...my co-host here,
    the" / "So-and-so, doing..."). That breaks two things: the burned-in caption
    (text cut off on screen) and clip boundary validation (which requires start
    and end on a complete sentence).

    Joins blocks until it finds closing punctuation, a speaker change (>>), or
    the duration/length limits from config.
    """
    from . import config

    segs, cur = [], None
    for b in blocks:
        if cur is None:
            cur = dict(b)
            continue
        ends = cur["text"].rstrip().endswith((".", "?", "!"))
        too_long = (b["end"] - cur["start"]) > config.SEG_MAX_DUR * 2
        too_big = len(cur["text"]) > config.SEG_MAX_CHARS * 2
        if ends or b["turn"] or too_long or too_big:
            segs.append(cur)
            cur = dict(b)
        else:
            cur["text"] = (cur["text"] + " " + b["text"]).strip()
            cur["end"] = b["end"]
    if cur:
        segs.append(cur)
    return segs


# Speaker labels recorded on each segment.
HOST = "host"
GUEST = "guest"


def resolve_speakers(segs: list) -> list:
    """Assigns speaker="host"/"guest" to each segment, looking at the episode.

    The episode opens with the hosts introducing the topic and the guest — so
    the first segment is always host. Each turn=True (the ">>" marker) switches
    the speaker from there on.

    The resolution is GLOBAL on purpose. Done inside one clip's slice it gets it
    wrong: a clip starting mid-answer contains no ">>" and would be attributed
    entirely to the host, zeroing the guest's speech fraction — the opposite of
    reality. Resolved here, each segment carries the absolute attribution and
    any later slice inherits it correctly.

    Mutates and returns the same list.
    """
    current = HOST
    for i, s in enumerate(segs):
        # The first segment is host even when marked with ">>" — the marker
        # there only says the transcript opened on a block of speech.
        if i > 0 and s.get("turn"):
            current = GUEST if current == HOST else HOST
        s["speaker"] = current
    return segs

"""Shared helpers: timestamps, VTT regexes, text cleanup and grouping.
"""
import re

from . import config

# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------
def srt_ts(seconds: float) -> str:
    """Seconds -> 'hh:mm:ss,ms' (SRT format)."""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def mmss(seconds: float) -> str:
    """Seconds -> 'mm:ss' (short label for curation)."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# VTT (YouTube's automatic rolling captions)
# ---------------------------------------------------------------------------
RE_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})")
RE_CUE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})")
RE_INLINE = re.compile(r"<(\d{2}:\d{2}:\d{2}\.\d{3})><c>(.*?)</c>")


def vtt_ts_to_sec(ts: str) -> float:
    h, m, s, ms = RE_TS.match(ts).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ---------------------------------------------------------------------------
# Text cleanup
# ---------------------------------------------------------------------------
# YouTube sound annotations. The tag list is an explicit alternation rather
# than "anything in brackets": transcripts also carry bracketed words that
# belong to the speech, and those must survive into the caption.
RE_SOUND_TAG = re.compile(
    r"\[\s*(music|laughter|applause|noise|silence|inaudible|crosstalk)\s*\]",
    re.IGNORECASE,
)


def strip_markup(txt: str) -> str:
    """Strips HTML entities and sound tags ([music], [laughter], ...)."""
    t = (txt.replace("&gt;", "").replace("&lt;", "").replace("&amp;", "&"))
    t = RE_SOUND_TAG.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# Spoken-only forms -> written form. The burned-in caption is read, not heard,
# so "gonna" on screen looks like a typo even when it transcribes the speech
# faithfully. Real contractions ("don't", "it's") are correct written English
# and are deliberately left alone.
_CONTRACTIONS = [
    (r"gonna", "going to"),
    (r"wanna", "want to"),
    (r"gotta", "got to"),
    (r"kinda", "kind of"),
]

# Hesitation noise, as standalone words only: 'ah' inside "yeah" must survive.
RE_FILLER = re.compile(r"\s+(uh|um|er|ah|hmm)\b\s*,?\s*", re.IGNORECASE)

# Discourse fillers, bounded to a comma-flanked or sentence-initial span.
# 'like' is also a verb and a preposition, and the filler has to be the whole
# span between the commas, so "tools, like Slack, are everywhere" is untouched.
_DISCOURSE_FILLER = r"you know|i mean|like"
RE_FILLER_MID = re.compile(rf",\s*(?:{_DISCOURSE_FILLER})\s*,", re.IGNORECASE)
RE_FILLER_END = re.compile(rf",\s*(?:{_DISCOURSE_FILLER})\s*(?=[.?!]|\s*$)",
                           re.IGNORECASE)
RE_FILLER_START = re.compile(
    rf"(?:(?<=^)|(?<=[.?!]))\s*(?:{_DISCOURSE_FILLER})\s*,\s*", re.IGNORECASE)


def _expand_contractions(t: str) -> str:
    """Expand spoken-only forms, keeping the sentence's initial capital."""
    for pat, target in _CONTRACTIONS:
        def _sub(m, target=target):
            return target.capitalize() if m.group(0)[0].isupper() else target

        t = re.sub(rf"\b{pat}\b", _sub, t, flags=re.IGNORECASE)
    return t


# Phonetic swaps automatic transcription makes on proper nouns. The same
# company comes back as Kestril, Cestril, Kestryl and Keztril — c/k, s/z,
# f/ph and i/y are the axes that actually vary in English.
_PHONETIC_EQUIVALENTS = [
    ("c", "[ck]"),
    ("k", "[ck]"),
    ("q", "[ckq]"),
    ("s", "[sz]"),
    ("z", "[sz]"),
    ("f", "(?:f|ph)"),
    ("i", "[iy]"),
    ("y", "[iy]"),
]


def _phonetic_pattern(name: str) -> str:
    """Regex matching the name and its transcription variants.

    Only table letters become character classes; every other letter stays
    literal, so the pattern cannot loosen far enough to swallow a real word
    ("kestrel" must not become "Kestril").
    """
    parts = []
    for ch in name.lower():
        for letter, char_class in _PHONETIC_EQUIVALENTS:
            if ch == letter:
                parts.append(char_class)
                break
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


# Company names that are also ordinary English words. Recasing them damages
# the sentence, so they stay out of the correction. Short and explicit list:
# guessing "is this a common word?" without a dictionary errs more often than
# it helps, and a name missing here only loses automatic capitalisation.
_COMMON_WORDS = {
    "apple", "orange", "amazon", "oracle", "square", "stripe", "slack",
    "meta", "shell", "sun", "gap", "target", "chase", "visa", "delta",
    "arc", "bolt", "lime",
}


def _is_common_word(name: str) -> bool:
    return name.strip().lower() in _COMMON_WORDS


def fix_proper_nouns(txt: str, names: list) -> str:
    """Rewrite proper nouns to the official spelling from episode.json.

    Transcription errs on proper nouns and the caption is burned into the
    video, so an uncorrected name ships (Cestril/Kestryl for Kestril).

    Only INVENTED names are corrected: a company called "Delta" or "Shell" is
    already transcribed right, and recasing it would damage the sentence ("the
    delta of the risk" turning into "the Delta of the risk").
    """
    for name in names or []:
        name = str(name).strip()
        if len(name) < 4:
            continue
        pat = re.compile(rf"\b{_phonetic_pattern(name)}\b", re.IGNORECASE)

        def _sub(m, name=name):
            # Already the official spelling apart from case: leave it.
            return name if m.group(0).lower() != name.lower() else m.group(0)

        matches = pat.findall(txt)
        # No wrong variant, only the name itself, perhaps lowercase: the case
        # is all there is to fix, and even that stays out when the name is an
        # ordinary word ("a shell company").
        if matches and all(a.lower() == name.lower() for a in matches):
            if not _is_common_word(name):
                txt = re.sub(rf"\b{re.escape(name)}\b", name, txt,
                             flags=re.IGNORECASE)
            continue
        txt = pat.sub(_sub, txt)
    return txt


def clean_caption(txt: str) -> str:
    """Clean a caption for display: drop repetition, fillers, spoken-only forms.

    E.g. 'we we shipped' -> 'we shipped'; strips uh/um/er/ah/hmm and the
    you-know, I-mean and like discourse fillers; 'gonna' -> 'going to'.
    (The audio is untouched -- only the text that appears on screen.)
    """
    t = " " + txt.strip() + " "
    # two passes to catch triples ('a a a')
    t = re.sub(r"\b(\w{1,5})\s+\1\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\w{1,5})\s+\1\b", r"\1", t, flags=re.IGNORECASE)
    t = RE_FILLER.sub(" ", t)
    t = RE_FILLER_MID.sub(", ", t)
    t = RE_FILLER_END.sub("", t)
    t = RE_FILLER_START.sub(" ", t)
    t = _expand_contractions(t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.?!])", r"\1", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Grouping words (t, word) -> segments {start, end, text}
# ---------------------------------------------------------------------------
def group_words_into_segments(words):
    """Groups a list of (time, word) into sentence segments.

    Breaks on pause (SEG_MAX_GAP), duration (SEG_MAX_DUR), length
    (SEG_MAX_CHARS) or closing punctuation.
    """
    segs = []
    cur = []
    for t, w in words:
        w = strip_markup(w)
        if not w:
            continue
        if not cur:
            cur = [(t, w)]
            continue
        prev = cur[-1][0]
        text = " ".join(x[1] for x in cur)
        ends = cur[-1][1].endswith((".", "?", "!"))
        too_long = (t - cur[0][0]) > config.SEG_MAX_DUR or len(text) > config.SEG_MAX_CHARS
        if (t - prev) > config.SEG_MAX_GAP or ends or too_long:
            segs.append({"start": round(cur[0][0], 3),
                         "end": round(prev + config.SEG_END_PAD, 3),
                         "text": text})
            cur = [(t, w)]
        else:
            cur.append((t, w))
    if cur:
        segs.append({"start": round(cur[0][0], 3),
                     "end": round(cur[-1][0] + config.SEG_END_PAD, 3),
                     "text": " ".join(x[1] for x in cur)})
    return segs

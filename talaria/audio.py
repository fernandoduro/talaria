"""Audio energy envelope — where speech pauses, so a clip cuts without leaking.

Clip times come from the transcript, whose resolution is 1 second. An end taken
from there lands on the boundary between two words and lets the attack of the
next one leak: the clip ended at 901.0 and the viewer heard the "Poucas" that
opens the following sentence.

The pause between words in continuous speech is short (~40ms in the measured
case), so a fixed margin does not solve it — backing off too far eats the last
usable syllable. The right way is to look at the audio and cut in the valley.

Requires ffmpeg on PATH. Without it the functions return the original time: the
render keeps working, just without the fine adjustment.
"""
from __future__ import annotations

import array
import math
import subprocess

# Analysis window. 20ms is short enough to find a pause between words and long
# enough that the RMS does not oscillate with the pitch period of the voice.
WINDOW_S = 0.02
RATE_HZ = 16000

# How far back the adjustment may look for the pause. Half a normal speech
# window: beyond that the clip loses content instead of gaining cleanliness.
SEARCH_S = 0.60


def _pcm(video_path: str, start: float, dur: float) -> array.array:
    """Extracts a stretch of audio as 16-bit mono PCM."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", video_path, "-ac", "1", "-ar", str(RATE_HZ), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    a = array.array("h")
    a.frombytes(out[:len(out) // 2 * 2])
    return a


def envelope(video_path: str, start: float, dur: float) -> list:
    """[(absolute_t, dB)] in WINDOW_S windows. dB relative to full scale."""
    a = _pcm(video_path, start, dur)
    win = int(RATE_HZ * WINDOW_S)
    points = []
    for i in range(len(a) // win):
        ch = a[i * win:(i + 1) * win]
        rms = math.sqrt(sum(x * x for x in ch) / len(ch)) + 1e-9
        points.append((start + i * WINDOW_S, 20 * math.log10(rms / 32768)))
    return points


# Energy below this counts as a pause. Speech stays above -25 dB; the room
# floor in these episodes hovers around -50 dB.
PAUSE_THRESHOLD_DB = -35.0


# Minimum silence for a pause to count as END OF SPEECH. Below this it is an
# internal pause — breath, hesitation, word separation — and cutting there
# leaves the sentence half finished (an 80ms valley at 2341.56 was internal;
# the sentence only ended at 2342.26, with 660ms of silence after it).
SILENCE_MIN_S = 0.25


def _silence_duration(points: list, i: int, threshold: float) -> float:
    """How long the energy stays below the threshold starting from `i`."""
    j = i
    while j < len(points) and points[j][1] <= threshold:
        j += 1
    return (j - i) * WINDOW_S


def valley_before(video_path: str, t: float, search: float = SEARCH_S) -> float:
    """Instant of the REAL pause nearest to `t`, looking backwards.

    The energy dropping is not enough: the silence has to LAST. In continuous
    speech the energy dips between words every 100ms, and cutting at the first
    dip splits the sentence. Only a pause followed by SILENCE_MIN_S of quiet counts.

    With no long pause in the window it returns `t` — better to leave it alone
    than to cut in the wrong place.
    """
    try:
        points = envelope(video_path, max(0.0, t - search), search)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return t
    if not points:
        return t
    for i in range(len(points) - 1, -1, -1):     # from the intended end backwards
        inst, db = points[i]
        if db <= PAUSE_THRESHOLD_DB and \
                _silence_duration(points, i, PAUSE_THRESHOLD_DB) >= SILENCE_MIN_S:
            # Cut at the BOTTOM of the pause, not the edge: the edge still has
            # the tail of the speech, and the bottom is where no seam is heard.
            j = i
            while j < len(points) and points[j][1] <= PAUSE_THRESHOLD_DB:
                j += 1
            return min(points[i:j], key=lambda p: p[1])[0]
    return t


def clips_mid_word(video_path: str, end: float, threshold_db: float = -25.0,
               window: float = 0.06) -> bool:
    """True if speech is still LOUD at the instant of the clip.

    All speech ends on a syllable, so looking 150ms back flags every clip —
    including the correct ones, where the last word is being pronounced and
    decays naturally. The right question is narrower: at the exact clip point,
    is the energy still at speech level?

    A 60ms window, and it only flags when the energy is NOT falling: a word
    ending decays; a word cut mid-way stops abruptly at a high level.
    """
    # Read with slack and keep the last windows: the mp4 comes out a few
    # milliseconds longer than asked for, and anchoring on the requested value
    # left the read with a single point — too few to see the energy decay.
    try:
        points = envelope(video_path, max(0.0, end - window * 3), window * 3)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
    n = max(2, int(round(window / WINDOW_S)))
    points = points[-n:]
    if len(points) < 2:
        return False
    dbs = [db for _, db in points]
    # Speech ending decays; speech cut off stops abruptly, still at high level.
    # Measured: a defective clip sits at -31/-28/-31 dB (stable); the correct
    # ones either end below -35 dB or plunge more than 10 dB in the last window
    # ("importadas": -25.8 -> -39.4).
    if dbs[-1] <= threshold_db - 10.0:
        return False                     # ended in silence
    return (dbs[0] - dbs[-1]) < 8.0      # did not decay enough

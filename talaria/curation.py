"""Iterative curation state — rounds until the approved-clip target is met.

State rules:
- a rejected stretch stays burned permanently, it never returns in any round;
- exclusion is by TIME OVERLAP, not by text — a clip 10s past a rejected one
  is essentially the same stretch;
- a time adjustment is not a rejection, it is approval with a correction.
"""
from __future__ import annotations

import json
import os
import re

from . import config, layout

FILE_NAME = "curation.json"

# Overlap fraction from which two spans count as "the same stretch".
OVERLAP_THRESHOLD = 0.30


def new_state(target: int = 5) -> dict:
    return {"target": target, "approved": [], "rejected": [], "rounds": 0}


def overlaps(a: tuple, b: tuple, threshold: float = OVERLAP_THRESHOLD) -> bool:
    """True if the (start, end) spans overlap above the threshold.

    The threshold is relative to the SMALLER of the two spans — that way a short
    clip contained in a long rejected one counts as an overlap.
    """
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    overlap = end - start
    if overlap <= 0:
        return False
    smaller = min(a[1] - a[0], b[1] - b[0])
    if smaller <= 0:
        return False
    return (overlap / smaller) >= threshold


def burned_spans(state: dict) -> list:
    """Every (start, end) span unavailable to new proposals."""
    spans = []
    for group in ("approved", "rejected"):
        for item in state.get(group, []):
            if "start" in item and "end" in item:
                spans.append((float(item["start"]), float(item["end"])))
    return spans


def is_burned(span: tuple, state: dict) -> bool:
    return any(overlaps(span, q) for q in burned_spans(state))


def slots_left(state: dict) -> int:
    return max(0, state["target"] - len(state.get("approved", [])))


def load(project_dir: str, target: int = 5) -> dict:
    path = layout.curation(project_dir)
    if not os.path.exists(path):
        return new_state(target)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, state: dict) -> str:
    path = layout.ensure_dir(layout.curation(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


# Approximate-figure markers. Lifted into a clip on its own, "roughly 570,
# 580" reads as a categorical claim the speaker never made. The digit must
# follow within the same sentence, so the 40-character window stops before
# sentence-ending punctuation.
#
# "about" and "some" are also an ordinary preposition and determiner, so
# "we talked about 3 things" warns falsely where no Portuguese marker could
# ("uns", "cerca de" have no second sense). Zero false positives on
# tests/fixtures/example.txt, and the alert fires before the attribution gate,
# so the base rate is recorded rather than narrowed.
RE_HEDGED_NUMBER = re.compile(
    r"\b(about|around|approximately|roughly|some|maybe|I think|"
    r"if I remember|more or less|or so|give or take)\b"
    r"[^.!?]{0,40}?\d",
    re.IGNORECASE,
)


def has_hedged_number(text: str) -> bool:
    """True if the text carries a number stated with hedging or doubt."""
    return bool(RE_HEDGED_NUMBER.search(text or ""))


def _valid_boundary(t: float, segs: list, tol: float = 0.5) -> bool:
    """True if t coincides with the start or end of some segment."""
    for s in segs:
        if abs(s["start"] - t) <= tol or abs(s["end"] - t) <= tol:
            return True
    return False


# Punctuation that closes a sentence. An ellipsis counts: the speech is left
# hanging, but not cut off mid-word.
RE_SENTENCE_END = re.compile(r"[.!?…]\s*$|\.\.\.\s*$")


def _ends_sentence(t: float, segs: list, tol: float = 0.5) -> bool:
    """True if t lands at the end of a segment whose text closes a sentence.

    The YouTube transcript breaks blocks by TIME, not by punctuation — a block
    can end mid-sentence and run on into the next. Matching only the block
    boundary (_valid_boundary) accepted a clip ending on a stray word; here the
    text's punctuation decides.
    """
    for s in segs:
        if abs(s["end"] - t) <= tol:
            return bool(RE_SENTENCE_END.search(s["text"].strip()))
    return False


def segments_in_clip(span: tuple, segs: list) -> list:
    """Segments intersecting the clip's (start, end) span."""
    start, end = span
    return [s for s in segs if s["end"] > start and s["start"] < end]


def guest_speech_fraction(span: tuple, segs: list) -> float:
    """Fraction of the clip's time in which the guest speaks.

    Reads the `speaker` field, resolved globally at parse time
    (txt_parse.resolve_speakers). It does NOT deduce the speaker by flipping a
    boolean inside the slice: the '>>' marker says THAT the speaker changed, not
    WHO speaks, and a clip starting mid-answer has no '>>' inside it at all —
    local alternation returned 0.0 for precisely the 100%-guest clips.

    Segments without `speaker` (vtt/Whisper origin, which has no turn marker, or
    data written before this fix) are left out of the calculation. If NO segment
    of the clip has `speaker`, the split is unmeasurable and the function returns
    1.0 — the value that does not trigger the alert in clip_warnings(). Returning
    0.0 would accuse every Whisper clip of "guest speaks 0%", the same false
    alert this fix exists to remove; when it cannot be measured, the judgement
    stays with the clips prompt and the manager.
    """
    inside = segments_in_clip(span, segs)
    if not inside:
        return 0.0
    total = guest_dur = 0.0
    for s in inside:
        speaker = s.get("speaker")
        if speaker is None:
            continue
        dur = min(s["end"], span[1]) - max(s["start"], span[0])
        if dur <= 0:
            continue
        total += dur
        if speaker == "guest":
            guest_dur += dur
    if not total:
        return 1.0        # unmeasurable: no alert
    return guest_dur / total


def sentence_ends(segs: list, start: float, lo: float, hi: float) -> list:
    """Sentence ends between `lo` and `hi` that give a valid clip duration.

    Returns [(instant, duration, context)] ordered by instant. It serves to pick
    where to end a clip without cutting speech mid-sentence — the work that was
    done by hand in this session, hunting for punctuation in the text.

    The instant is interpolated from the character position inside the block:
    the transcript carries no per-word time. Check with `audio.valley_before()`
    before settling, because the interpolation is off by tens of milliseconds.
    """
    out = []
    for s in segs:
        if s["end"] < lo or s["start"] > hi:
            continue
        txt = s["text"]
        if not txt:
            continue
        dur = s["end"] - s["start"]
        for m in re.finditer(r"[.!?…]", txt):
            inst = s["start"] + dur * (m.end() / len(txt))
            if not (lo <= inst <= hi):
                continue
            d = inst - start
            if config.CLIP_MIN_S <= d <= config.CLIP_MAX_S:
                out.append((round(inst, 2), round(d, 1),
                            txt[max(0, m.end() - 50):m.end()].strip()))
    return sorted(out)


def validate_clip(span: tuple, segs: list, state: dict) -> tuple:
    """Validates a clip proposal. Returns (ok, [messages]).

    Checks what code can verify; the editorial judgement stays with the clips
    prompt and the manager.
    """
    msgs = []
    start, end = span
    dur = end - start

    if dur < config.CLIP_MIN_S:
        msgs.append(f"duration {dur:.0f}s below the minimum of "
                    f"{config.CLIP_MIN_S}s")
    elif dur > config.CLIP_MAX_S:
        msgs.append(f"duration {dur:.0f}s above the maximum of "
                    f"{config.CLIP_MAX_S}s")

    # The clip must not start NOR end mid-sentence.
    # The end was once only a warning, on the assumption the tail would be
    # "trimmed at render" — the render cuts at the exact time, so nothing was
    # trimmed and the video shipped with the last sentence half finished.
    if segs and not _valid_boundary(start, segs):
        msgs.append(f"start {start:.1f}s does not land on a sentence boundary")

    # Closing punctuation is only required when the end coincides with a block
    # end. An end in the MIDDLE of a block is legitimate (the manager trims the
    # tail where the sentence ends, even if the block runs on) and is allowed.
    if segs and _valid_boundary(end, segs) and not _ends_sentence(end, segs):
        msgs.append(f"end {end:.1f}s does not close a sentence "
                    f"(it cuts the speech mid-way)")

    if state and is_burned(span, state):
        msgs.append("overlaps a burned span (approved or rejected)")

    return (not msgs), msgs


# Markers of someone speaking about their OWN company in the first person. If a
# segment labelled "host" is full of them, the speaker there is the guest and
# the attribution has slipped.
#
# Bare we/our/us are deliberately absent: host register uses them constantly
# ("tell us how it started", "we are recording another episode"), which put the
# host first-person fraction of tests/fixtures/example.txt at 0.606 against the
# 0.30 threshold below. Narrowed to own-company phrases the same fixture
# measures 0.000; a host segment carrying swapped guest speech still measures
# 0.857. The trade is recall: a guest stretch that only says "we worked
# somewhere else" no longer registers, and no transcript with genuinely swapped
# labels exists here to measure that loss on.
RE_FIRST_PERSON = re.compile(
    r"\b(my company|our company|our team|our own|my co-?founder|"
    r"our first hire)\b",
    re.IGNORECASE,
)

# Above this fraction the attribution does not deserve trust. 0.30 was tuned
# against the Portuguese markers ("a gente", "nosso"); the English set above is
# narrowed to a comparable base rate, measured on the repository's own fixture.
SUSPECT_ATTRIBUTION_THRESHOLD = 0.30


def attribution_trustworthy(segs: list) -> bool:
    """False when the `speaker` field looks swapped across the whole episode.

    The parser resolves the speaker once, over the whole episode; one short host
    backchannel can misalign everything after it (stretches that were 100% guest
    came out as "host"). Alerts reading `speaker` would lie, and a lying alert
    trains the operator to ignore the output — better to stay quiet.
    """
    host_total = first_person = 0.0
    for s in segs or []:
        if s.get("speaker") != "host":
            continue
        dur = s["end"] - s["start"]
        host_total += dur
        if RE_FIRST_PERSON.search(s.get("text") or ""):
            first_person += dur
    if host_total <= 0:
        return True
    return (first_person / host_total) < SUSPECT_ATTRIBUTION_THRESHOLD


# Seconds of host at the opening beyond which the clip becomes a question with
# an answer rather than an answer. One clip opened with 47s of question.
HOST_OPENING_MAX_S = 8.0


def host_opening(span: tuple, segs: list) -> float:
    """How many seconds of host speech open the clip, before the guest.

    Zero when the clip already opens on the guest or when there is no way to
    know who speaks (`speaker` absent) — the alert must not fire in the dark.
    """
    inside = segments_in_clip(span, segs)
    total = 0.0
    for s in inside:
        speaker = s.get("speaker")
        if speaker is None:
            return 0.0
        if speaker != "host":
            break
        total += min(s["end"], span[1]) - max(s["start"], span[0])
    return total


def clip_warnings(span: tuple, segs: list) -> list:
    """Warnings that do not invalidate the clip, but need a check."""
    alerts = []
    inside = segments_in_clip(span, segs)
    for s in inside:
        if has_hedged_number(s["text"]):
            alerts.append(f"hedged figure at {s['start']:.0f}s: "
                          f"\"{s['text'][:60]}\"")
    # The two alerts below read `speaker`; without trustworthy attribution they
    # would flag a good clip. Warned once that the check did not run.
    if not attribution_trustworthy(segs):
        return alerts       # warned once per episode, in cmd_curate

    frac = guest_speech_fraction(span, segs)
    if frac < config.GUEST_SPEECH_MIN:
        alerts.append(f"guest speaks only {frac*100:.0f}% of the clip")

    seg_host = host_opening(span, segs)
    if seg_host >= HOST_OPENING_MAX_S:
        alerts.append(
            f"clip opens with {seg_host:.0f}s of host speech — the cold "
            "viewer leaves before the guest talks"
        )
    return alerts


# Clip kinds, in order of preference.
KINDS = ["story", "thesis", "advice", "personal"]


def approve(state: dict, clip: dict) -> dict:
    """Records an approved clip. A time adjustment is not a rejection.

    Refuses a clip overlapping one ALREADY APPROVED: two videos carrying the
    same stretch compete with each other in distribution. Two approved clips
    shared 74s because nothing checked it here — `validate_clip` looks at burned
    spans, which include approved ones, but a direct `approve()` call escaped it.

    Re-approving the SAME slug is a time adjustment, not a duplicate: it replaces.
    """
    span = (float(clip["start"]), float(clip["end"]))
    for i, approved_clip in enumerate(state["approved"]):
        if approved_clip.get("slug") == clip.get("slug"):
            state["approved"][i] = clip      # time adjustment
            return state
        # Zero threshold: between APPROVED clips any overlap already means a
        # stretch of video repeated in two clips. The 30% OVERLAP_THRESHOLD
        # exists to decide whether a proposal is "the same stretch" as something
        # burned — a different question, a different tolerance.
        if overlaps(span, (float(approved_clip["start"]), float(approved_clip["end"])), threshold=0.0):
            raise ValueError(
                f"clip {clip.get('slug')} overlaps approved clip "
                f"{approved_clip.get('slug')} ({approved_clip['start']:.0f}-{approved_clip['end']:.0f}s)"
            )
    if len(state["approved"]) >= state["target"]:
        raise ValueError(f"target of {state['target']} clips already met")
    state["approved"].append(clip)
    return state


def reject(state: dict, clip: dict, reason: str) -> dict:
    """Burns the stretch permanently, with the reason as free text."""
    state["rejected"].append({
        "start": float(clip["start"]),
        "end": float(clip["end"]),
        "summary": clip.get("summary", clip.get("screen_text", "")),
        "reason": reason,
    })
    return state


def composition(state: dict) -> dict:
    """How many approved clips of each kind (diversity)."""
    comp = {t: 0 for t in KINDS}
    for c in state["approved"]:
        t = c.get("kind")
        if t in comp:
            comp[t] += 1
    return comp


def missing_kinds(state: dict) -> list:
    """Kinds with no approved clip — feeds the diversity warning."""
    return [t for t, n in composition(state).items() if n == 0]


def reasons(state: dict) -> list:
    """Rejection reasons without repetition — context for the next round."""
    seen, out = set(), []
    for r in state.get("rejected", []):
        m = (r.get("reason") or "").strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def is_closed(state: dict) -> bool:
    """True once the approved-clip target has been met."""
    return len(state.get("approved", [])) >= state["target"]


def to_moments(state: dict) -> list:
    """Converts the approved clips into the moments.json the render consumes.

    The render uses only slug/start/end; the other fields are production content
    that has to survive as far as publication.
    """
    if not state.get("approved"):
        raise ValueError("no approved clip — nothing to export")
    return [dict(c) for c in state["approved"]]


def save_moments(project_dir: str, state: dict) -> str:
    """Writes moments.json into the project directory and returns the path."""
    moments = to_moments(state)
    path = layout.ensure_dir(layout.moments(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(moments, f, ensure_ascii=False, indent=2)
    return path

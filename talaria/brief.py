"""Builds the reading packets a language model consumes in a session.

Joins the versioned prompt + episode metadata + transcript into a single file,
replacing the manual copy-paste done for every episode.
"""
from __future__ import annotations

import json
import os

from . import curation as cur
from . import episode, layout, utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(ROOT, "prompts")


def readable_transcript(project_dir: str) -> str:
    """Transcript with [mm:ss] per segment, for locating clips."""
    path = layout.transcript(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]
    lines = []
    for s in segs:
        marker = ">> " if s.get("turn") else ""
        lines.append(f"[{utils.mmss(s['start'])}] {marker}{s['text']}")
    return "\n".join(lines)


def readable_metadata(project_dir: str) -> str:
    """The prompt's metadata block, filled in from episode.json."""
    ep = episode.load(project_dir)
    guests = ep.get("guests") or []
    names = "; ".join(
        f"{c.get('name','')} ({c.get('role','')})" for c in guests if c.get("name")
    )
    links = "; ".join(c.get("linkedin", "") for c in guests if c.get("linkedin"))
    topics = ", ".join(ep.get("topics") or [])
    return (
        f"- Season: {ep['season']}\n"
        f"- Episode number: {int(ep['episode']):02d}\n"
        f"- Code: {episode.code(ep)}\n"
        f"- Guest(s) and role: {names}\n"
        f"- Company or institution: {ep['company']}\n"
        f"- Recording city/state: {ep['city']}/{ep['uf']}\n"
        f"- Guest(s) LinkedIn: {links}\n"
        f"- Conversation topics: {topics}\n"
    )


def fill_template(template: str, transcript: str, metadata: str,
              curation: str = "", clips: str = "") -> str:
    """Replaces the prompt placeholders with the episode content."""
    return (template
            .replace("{{TRANSCRIPT}}", transcript)
            .replace("{{METADATA}}", metadata)
            .replace("{{CURATION}}", curation)
            .replace("{{CLIPS}}", clips))


def readable_curation(state: dict) -> str:
    """Curation state as text, injected into the clips prompt."""
    approved = state.get("approved", [])
    rejected = state.get("rejected", [])

    if not approved and not rejected:
        return ("FIRST ROUND — no clip judged yet.\n"
                "Propose 10 stretches, ordered strongest to weakest.")

    lines = [
        f"Round: {state.get('rounds', 0)}",
        f"Target: {state['target']} clips",
        f"Approved: {len(approved)}",
        f"SLOTS LEFT: {cur.slots_left(state)} — propose exactly this many.",
        "",
        "COMPOSITION BY KIND:",
    ]
    for kind, n in cur.composition(state).items():
        lines.append(f"  {kind}: {n}")
    missing = cur.missing_kinds(state)
    if missing:
        lines.append(f"  MISSING KINDS (prioritise): {', '.join(missing)}")

    lines.append("")
    lines.append("BURNED SPANS — propose nothing that overlaps them:")
    for c in approved:
        lines.append(f"  [{utils.mmss(c['start'])}-{utils.mmss(c['end'])}] "
                      f"APPROVED: {c.get('screen_text', c.get('slug', ''))}")
    for r in rejected:
        lines.append(f"  [{utils.mmss(r['start'])}-{utils.mmss(r['end'])}] "
                      f"REJECTED ({r.get('reason', '')}): {r.get('summary', '')}")

    ms = cur.reasons(state)
    if ms:
        lines.append("")
        lines.append("ACCUMULATED REJECTION REASONS — apply them as a filter:")
        for m in ms:
            lines.append(f"  - {m}")

    return "\n".join(lines)


def _read_prompt(name: str) -> str:
    """Reads a versioned prompt from the prompts/ directory."""
    path = os.path.join(PROMPTS_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"prompt not found: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def build(project_dir: str, kind: str) -> str:
    """kind: 'materials' or 'clips'. Returns the path of the file written."""
    if kind not in ("materials", "clips"):
        raise ValueError("kind must be 'materials' or 'clips'")
    template = _read_prompt(f"{kind}.md")
    state_txt = ""
    if kind == "clips":
        state_txt = readable_curation(cur.load(project_dir))
    content = fill_template(
        template,
        transcript=readable_transcript(project_dir),
        metadata=readable_metadata(project_dir),
        curation=state_txt,
    )
    out = layout.ensure_dir(layout.brief(project_dir, kind))
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out


def clip_speech(project_dir: str, clip: dict) -> str:
    """The clip's literal speech, for choosing the quote.

    Includes every segment that OVERLAPS the window, trimming the text at the
    boundary — the same rule as `render._segments_in_cut`, so the packet shows
    the speech that became video.

    Requiring full containment hid the last sentence of every clip, because the
    transcript has ~8s blocks and the boundary almost never coincides with them.
    That is exactly where the punchline usually sits: in one clip the packet
    ended at "we got to the factory and you did not" while the video went on.

    The text comes RAW (no `clean_caption`): the excerpt is chosen over what the
    person actually said. Cleanup comes later, in `post --generate`.
    """
    from .render import _trim_text

    path = layout.transcript(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]

    parts = []
    for s in segs:
        start, end = s["start"], s["end"]
        if end <= clip["start"] or start >= clip["end"]:
            continue
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        if start < clip["start"] or end > clip["end"]:
            dur = end - start
            if dur > 0:
                txt = _trim_text(
                    txt,
                    (max(start, clip["start"]) - start) / dur,
                    (min(end, clip["end"]) - start) / dur,
                )
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


def readable_clips(project_dir: str, clips: list) -> str:
    """Block with each selected clip's speech, for the curation session."""
    parts = []
    for c in clips:
        parts.append(
            f"### {c['slug']}  [{utils.mmss(c['start'])}–{utils.mmss(c['end'])}]\n\n"
            f"- Kind: {c.get('kind', '')}\n"
            f"- Video screen text: {c.get('screen_text', '')}\n\n"
            f"Literal speech:\n\n{clip_speech(project_dir, c)}\n"
        )
    return "\n".join(parts)


def build_posts(project_dir: str, clips: list) -> str:
    """Writes brief_posts.md with the prompt and the chosen clips' speech.

    Separate from `build()` because the posts packet does not get the whole
    transcript: the quote comes from already-approved clips, and sending the
    entire episode would invite picking speech that never became video.
    """
    from . import config
    limit = (
        f"At most {config.POST_QUOTE_MAX_LINES} lines per card, about "
        f"100 characters. The reference quote has 97.\n"
    )
    content = fill_template(
        _read_prompt("posts.md"),
        transcript="",
        metadata=readable_metadata(project_dir) + "\n" + limit,
        clips=readable_clips(project_dir, clips),
    )
    out = layout.ensure_dir(layout.brief(project_dir, "posts"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out

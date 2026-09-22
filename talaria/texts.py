"""texts.json — publishing materials and the thumbnail's input.

The thumbnail text derives from episode.json (line 1 = company, or the first
topic when there is no company; line 2 = T[N]E[NN]), but texts.json may
override any field when the model proposes something better during the
materials step.
"""
from __future__ import annotations

import json
import os

from . import config, episode, layout

FILE_NAME = "texts.json"


def load(project_dir: str) -> dict:
    """Reads the project's texts.json. Returns an empty dict if absent."""
    path = layout.texts(project_dir)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, data: dict) -> str:
    """Writes the project's texts.json and returns the path written."""
    path = layout.ensure_dir(layout.texts(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def thumb_args(project_dir: str) -> dict:
    """Thumbnail arguments, derived from the episode, overridden by texts.json."""
    ep = episode.load(project_dir)
    code = episode.code(ep)
    guests = ep.get("guests") or []
    credits = " & ".join(c.get("name", "") for c in guests if c.get("name"))

    # In an episode with no external guest (hence no company), line 1
    # takes the episode topic.
    topics = ep.get("topics") or []
    l1 = ep.get("company", "") or (topics[0] if topics else "")

    args = {
        "badge": f"{config.SHOW_NAME} • {code}",
        "l1": l1,
        "l2": code,
        "credits": credits,
        "subtitle": f"{ep.get('city','')}/{ep.get('uf','')}",
    }
    args.update(load(project_dir).get("thumb", {}))
    return args


def build_kwargs(project_dir: str) -> dict:
    """Arguments in the shape thumbnail.build_thumbnail expects.

    Single translation point for l1/l2 -> headline_l1/headline_l2: mapping by
    hand at the call site drops a field silently (credits and subtitle default
    to "" and get skipped with no warning).
    """
    args = thumb_args(project_dir)
    return {
        "badge": args["badge"],
        "headline_l1": args["l1"],
        "headline_l2": args["l2"],
        "credits": args["credits"],
        "subtitle": args["subtitle"],
    }

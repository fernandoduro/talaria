"""Record of what has already been published — the lock against duplicates.

The record's unit is (platform, slug): one clip publishes to YouTube AND Reels,
and if only one of the two went through, the next day's retry publishes only
the one that was missing; a per-item pending flag would republish the other.

Each success is written IMMEDIATELY, atomically. Recording only at the end of
the batch leaves a window: the process dies partway and the next run duplicates
what had already gone out — a duplicate post cannot be fixed after publishing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import config, layout


def load(pd: str) -> dict:
    """Reads the record. A corrupt file ABORTS — fail closed.

    Invalid JSON is never treated as "nothing published yet": that would
    republish the whole history. `projects/` is git-ignored, so there is no
    backup in git — the message tells the manager to check the platform
    profiles before recreating the file.
    """
    path = layout.published(pd)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"{path} is corrupt ({e}). I will not assume 'nothing "
                f"published' — that would republish everything. Check what is "
                f"already live on the platform profiles and recreate the file "
                f"by hand."
            )


def is_published(reg: dict, platform: str, slug: str) -> bool:
    return any(r.get("slug") == slug for r in reg.get(platform, []))


def record(pd: str, platform: str, slug: str, post_id: str,
             url: str) -> str:
    """Appends ONE publication and writes it immediately, atomically.

    temp + os.replace on the same filesystem: either the whole new file or the
    old one intact — never a half-written JSON (which `load` would refuse).
    """
    reg = load(pd)
    reg.setdefault(platform, []).append({
        "slug": slug,
        "id": post_id,
        "url": url,
        "published_at": dt.datetime.now(
            ZoneInfo(config.PUBLISH_TZ)).isoformat(timespec="seconds"),
    })
    path = layout.ensure_dir(layout.published(pd))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path

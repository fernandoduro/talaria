"""Publishing schedule: which piece goes out on which day.

The calendar is an editorial decision — the manager writes
decisions/schedule.json the way he writes posts.json. This module validates it
against the sources (moments.json, posts.json) BEFORE any publication: a
mistyped slug would publish the wrong clip, and that has no fix once live.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import config, layout, post_instagram, published

# Platforms per item kind. The names are those of the publish/ folders and the
# published.json keys — one spelling, from file to record.
PLATFORMS = {
    "clip": ("youtube_shorts", "instagram_reels"),
    "post": ("instagram_posts",),
}

# An Instagram carousel accepts 2-10 images.
CAROUSEL_MAX = 10


def today() -> dt.date:
    """Today in the configured timezone — never the machine's naive date."""
    return dt.datetime.now(ZoneInfo(config.PUBLISH_TZ)).date()


def platforms_of(item: dict) -> tuple:
    return PLATFORMS[item["kind"]]


def date_of(item: dict) -> dt.date:
    """The item's date as a date. fromisoformat validates format AND real day."""
    return dt.date.fromisoformat(item["date"])


def moments(pd: str) -> list:
    """The clips curation exported, or an error naming the command."""
    path = layout.moments(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} does not exist. Run 'python run.py curate --project "
            f"<slug> --export' before scheduling clips."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(pd: str) -> list:
    """Reads and validates the schedule. Any invalid item aborts the load."""
    path = layout.schedule(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} does not exist. Write the publishing schedule: "
            f'{{"schedule": [{{"date": "YYYY-MM-DD", "kind": "clip|post", '
            f'"slug": "..."}}]}}'
        )
    with open(path, encoding="utf-8") as f:
        items = (json.load(f) or {}).get("schedule") or []
    if not items:
        raise ValueError(f"{path} has no item in 'schedule'")

    # Sources loaded on demand: a posts-only schedule needs no moments.json.
    clips = posts = None
    seen = set()
    for i, item in enumerate(items, start=1):
        slug = item.get("slug") or ""
        kind = item.get("kind") or ""
        where = f"schedule item {i} ('{slug or '?'}')"
        if kind not in PLATFORMS:
            raise ValueError(f"{where}: kind {kind!r} — use 'clip' or 'post'")
        if not slug:
            raise ValueError(f"{where}: no slug")
        # The slug becomes a filename inside publish/. A slash or a `..` takes
        # it out of the episode folder, and then publish finds an mp4 from
        # outside the project, passes the pre-check and publishes the wrong
        # piece — with the outside text becoming a public description. A clip
        # slug is hand-typed in curation.json and nothing validates it before here.
        if "/" in slug or "\\" in slug or slug.strip(". ") != slug:
            raise ValueError(
                f"{where}: the slug cannot carry a slash nor start/end with "
                f"a dot — it becomes a filename in publish/, and would then "
                f"point outside the episode folder"
            )
        # The key is (kind, slug), not the slug: a quote post inherits the slug
        # of the clip it quotes (that is how `post --clips` names it), and clip
        # plus post of the same stretch on the same schedule is the common case,
        # not a repetition. Publishing and recording already split them by platform.
        if (kind, slug) in seen:
            raise ValueError(
                f"{where}: {kind} appears twice — to change the date, edit "
                f"the existing item instead of repeating it"
            )
        seen.add((kind, slug))
        try:
            date_of(item)
        except (TypeError, ValueError):
            raise ValueError(
                f"{where}: date {item.get('date')!r} invalid — use "
                f"YYYY-MM-DD of a day that exists"
            )
        if kind == "clip":
            if clips is None:
                clips = {m.get("slug") for m in moments(pd)}
            if slug not in clips:
                raise ValueError(
                    f"{where}: not in {layout.moments(pd)} — "
                    f"available clips: {', '.join(sorted(clips))}"
                )
        else:
            if posts is None:
                posts = {p.get("slug"): p for p in post_instagram.load(pd)}
            if slug not in posts:
                raise ValueError(
                    f"{where}: not in {layout.posts(pd)} — "
                    f"available posts: {', '.join(sorted(posts))}"
                )
            cards = posts[slug].get("cards") or []
            if len(cards) > CAROUSEL_MAX:
                raise ValueError(
                    f"post '{slug}' has {len(cards)} cards — the Instagram "
                    f"carousel accepts at most {CAROUSEL_MAX}; break it into "
                    f"two posts"
                )
    return items


def pending(pd: str, day: dt.date = None, only: list = None,
             platforms: list = None) -> list:
    """(item, platform) pairs due by `day` and not yet published.

    The unit is (slug, platform), not the item: one clip publishes to YouTube
    AND Reels, and if only one went through, the retry publishes only the one
    that was missing — a per-item pending flag would republish the other.

    `only` ignores the date filter (bringing forward, testing), but NEVER the
    published.json lock — republishing means editing the record by hand, on
    purpose, not a flag that can be typed by mistake.

    `only=None` means "no filter"; `only=[]` means "filter to nothing" and
    returns empty. The distinction is `is not None` on purpose: a caller that
    composes the list from an empty flag would ask for the whole schedule
    unintentionally, and publish the entire day believing it had restricted
    itself to one slug.

    `platforms` restricts which platforms go out. It serves publishing when only
    one is configured: a clip demands both YouTube AND Instagram credentials, so
    without it the whole clip stalls. What does not go out stays pending — the
    lock is per (slug, platform), so the rest goes later.

    Overdue (date < day, not published) stays pending: forgetting to run
    yesterday must not lose the publication.
    """
    day = day or today()
    if platforms is not None:
        known = {p for pls in PLATFORMS.values() for p in pls}
        unknown_platforms = sorted(set(platforms) - known)
        if unknown_platforms:
            raise ValueError(
                f"unknown platform: {', '.join(unknown_platforms)} — "
                f"use {', '.join(sorted(known))}"
            )
    items = load(pd)
    if only is not None:
        unknown_slugs = sorted(set(only) - {i["slug"] for i in items})
        if unknown_slugs:
            raise ValueError(
                f"--only: {', '.join(unknown_slugs)} not in the schedule "
                f"({layout.schedule(pd)})"
            )
        items = [i for i in items if i["slug"] in set(only)]
    else:
        items = [i for i in items if date_of(i) <= day]

    reg = published.load(pd)
    pairs = []
    for item in items:
        for pl in platforms_of(item):
            if platforms is not None and pl not in platforms:
                continue
            if not published.is_published(reg, pl, item["slug"]):
                pairs.append((item, pl))
    return pairs

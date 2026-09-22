"""Publishing orchestrator: what the schedule calls for today, per platform.

A complete pre-check BEFORE the first upload — the same contract as
post_instagram.generate(), for the same reason: finding out at the third item
that a render was missing, with the first two already live, is the state this
module forbids.

Each success is recorded IMMEDIATELY in published.json; a failure on one
platform does not block the others — the final summary counts both.
"""
from __future__ import annotations

import os
import re

from . import (schedule, caption, layout, post_instagram, published,
               publish_instagram, publish_youtube)

# Platform limits: validated here, before calling the API.
YT_TITLE_MAX = 100
YT_DESCRIPTION_MAX = 5000
IG_CAPTION_MAX = 2200

# Credentials required per platform — the pre-check only demands those of the
# platforms the day actually uses.
_CREDENTIALS = {
    "youtube_shorts": ("YT_CLIENT_SECRET_PATH", "YT_REFRESH_TOKEN"),
    "instagram_reels": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
    "instagram_posts": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
}

_MP4_SUFFIX = {"youtube_shorts": "_short.mp4", "instagram_reels": "_reel.mp4"}


def _mp4(pd: str, platform: str, slug: str) -> str:
    """Path of the rendered clip, with the slug sanitised.

    `schedule.load` already refuses a slug with a slash, but the sanitising
    stays here too: it is the same treatment the post PNGs get, and the
    consequence of a slug escaping the folder is publishing a file from outside
    the project — too expensive to rest on a single barrier.
    """
    return os.path.join(layout.platform(pd, platform),
                        post_instagram.file_slug(slug)
                        + _MP4_SUFFIX[platform])


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _moments_by_slug(pd: str) -> dict:
    return {m.get("slug"): m for m in schedule.moments(pd)}


def _post_pngs(pd: str, slug: str) -> list:
    """A post's PNGs, in carousel order (numeric, not alphabetical)."""
    fname = post_instagram.file_slug(slug)
    folder = layout.posts_png(pd)
    single = os.path.join(folder, f"post_{fname}.png")
    if os.path.exists(single):
        return [single]
    if not os.path.isdir(folder):
        return []
    pattern = re.compile(rf"^post_{re.escape(fname)}_(\d+)\.png$")
    numbered = []
    for name in os.listdir(folder):
        m = pattern.match(name)
        if m:
            numbered.append((int(m.group(1)), name))
    numbered.sort()
    return [os.path.join(folder, n) for _, n in numbered]


def _post_txt(pd: str, slug: str) -> str:
    fname = post_instagram.file_slug(slug)
    return os.path.join(layout.posts_png(pd), f"post_{fname}.txt")


def precheck(pd: str, pairs: list) -> list:
    """Errors that would stop ANY of the day's items. Empty list = ok.

    Runs before the first upload: missing file, absent or overlong title,
    caption above the limit, undefined credential. The message always says
    which command or file fixes it.
    """
    errors = []
    has_clip = any(item["kind"] == "clip" for item, _ in pairs)
    moments = _moments_by_slug(pd) if has_clip else {}

    for item, pl in pairs:
        slug = item["slug"]
        if item["kind"] == "clip":
            video = _mp4(pd, pl, slug)
            if not os.path.exists(video):
                errors.append(f"{slug} ({pl}): {video} does not exist — "
                             f"run 'render' first")
                continue
            txt = caption.txt_path(video)
            if not os.path.exists(txt):
                errors.append(f"{slug} ({pl}): {txt} does not exist — "
                             f"regenerate the clip with 'render'")
                continue
            text = _read(txt)
            if pl == "youtube_shorts":
                title = (moments.get(slug) or {}).get("title") or ""
                if not title.strip():
                    errors.append(
                        f"{slug}: no 'title' in moments.json — YouTube "
                        f"requires a title; fill the field in curation.json "
                        f"and run 'curate --export'")
                elif len(title) > YT_TITLE_MAX:
                    errors.append(f"{slug}: title with {len(title)} chars — "
                                 f"YouTube accepts {YT_TITLE_MAX}")
                if len(text) > YT_DESCRIPTION_MAX:
                    errors.append(f"{slug}: description with {len(text)} "
                                 f"chars — YouTube accepts "
                                 f"{YT_DESCRIPTION_MAX}")
            elif len(text) > IG_CAPTION_MAX:
                errors.append(f"{slug} ({pl}): caption with {len(text)} chars "
                             f"— Instagram accepts {IG_CAPTION_MAX}")
        else:
            pngs = _post_pngs(pd, slug)
            if not pngs:
                errors.append(f"{slug} (instagram_posts): no PNG in "
                             f"{layout.posts_png(pd)} — run 'post --generate' "
                             f"first")
                continue
            txt = _post_txt(pd, slug)
            if not os.path.exists(txt):
                errors.append(f"{slug} (instagram_posts): {txt} does not "
                             f"exist — regenerate with 'post --generate'")
            elif len(_read(txt)) > IG_CAPTION_MAX:
                errors.append(f"{slug} (instagram_posts): caption above "
                             f"{IG_CAPTION_MAX} chars")

    envs = set()
    for _, pl in pairs:
        envs.update(_CREDENTIALS[pl])
    for name in sorted(envs):
        if not os.environ.get(name):
            errors.append(f"variable {name} not defined in the environment "
                         f"(.env)")

    # A wrong privacy value would only surface after the upload, with the video
    # already live under a privacy nobody asked for.
    if any(pl == "youtube_shorts" for _, pl in pairs):
        try:
            publish_youtube.privacy()
        except ValueError as e:
            errors.append(str(e))
    return errors


def _publish_pair(pd: str, item: dict, pl: str, moments: dict) -> dict:
    """Publishes ONE (item, platform) pair. Returns {"id", "url"}."""
    slug = item["slug"]
    if pl == "youtube_shorts":
        video = _mp4(pd, pl, slug)
        m = moments[slug]
        return publish_youtube.upload(video, m["title"],
                                      _read(caption.txt_path(video)))
    if pl == "instagram_reels":
        video = _mp4(pd, pl, slug)
        r = publish_instagram.publish_reel(video, _read(caption.txt_path(video)))
        return {"id": r["id"], "url": r.get("permalink", "")}
    pngs = _post_pngs(pd, slug)
    r = publish_instagram.publish_post(pngs, _read(_post_txt(pd, slug)))
    return {"id": r["id"], "url": r.get("permalink", "")}


def execute(pd: str, only: list = None, day=None,
             platforms: list = None) -> list:
    """Publishes the day's pending pairs. Returns one result per pair.

    A failed pre-check aborts EVERYTHING before the first upload. After it,
    each pair is independent: a failure in one does not block the others (the
    exception becomes a result with ok=False), and each success is recorded in
    published.json IMMEDIATELY — a process killed mid-batch duplicates nothing
    tomorrow.

    There are three outcomes, not two. Publishing and recording are separate
    steps, and what happens between them matters:

    - `ok=False`             — it did not go live; back in tomorrow's queue.
    - `ok=True`              — it went live and was recorded.
    - `ok=True` +
      `record_failed=True` — IT WENT LIVE and the record failed. It comes out
                               as published on purpose: marking failure would
                               send the pair to tomorrow's queue and publish
                               the piece again. The `id` comes in the result
                               so the manager can add it to published.json.
    """
    pairs = schedule.pending(pd, day=day, only=only,
                                platforms=platforms)
    if not pairs:
        return []

    errors = precheck(pd, pairs)
    if errors:
        raise ValueError("pre-check failed — nothing was published:\n- "
                         + "\n- ".join(errors))

    has_clip = any(item["kind"] == "clip" for item, _ in pairs)
    moments = _moments_by_slug(pd) if has_clip else {}
    results = []
    for item, pl in pairs:
        slug = item["slug"]
        base = {"slug": slug, "platform": pl, "date": item["date"]}
        try:
            r = _publish_pair(pd, item, pl, moments)
        except Exception as e:  # noqa: BLE001 — one pair failing blocks no other
            results.append({**base, "ok": False, "error": str(e)})
            print(f"[publish] !! {pl}: {slug}: {e}")
            continue

        url = r.get("url", "")
        # From here down the piece IS ALREADY LIVE. A record failure cannot
        # become ok=False: pending comes from absence in published.json, so the
        # pair would return tomorrow and publish again — the duplicate that has
        # no fix. It comes out as published, with the id at hand for the repair.
        try:
            published.record(pd, pl, slug, r["id"], url)
        except Exception as e:  # noqa: BLE001
            results.append({**base, "ok": True, "url": url, "id": r["id"],
                               "record_failed": True, "error": str(e)})
            print(f"[publish] !! {pl}: {slug} WAS PUBLISHED "
                  f"({url or r['id']}) but did not enter published.json: {e}")
            print(f"[publish]    Do NOT run publish again before adding this "
                  f"id by hand — or {pl} publishes the piece twice.")
            continue

        results.append({**base, "ok": True, "url": url})
        print(f"[publish] ok {pl}: {slug} -> {url or r['id']}")
    return results

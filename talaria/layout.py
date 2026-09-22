"""Where every project file lives. The single authority over paths.

Before this each module built its own with a literal string
(`os.path.join(project_dir, "moments.json")` appeared in 5 files), and the
result was a dozen loose files in the episode root, of different natures
mixed together.

The folder is organised by NATURE:

    <slug>/episode.json      the manager fills it in by hand — it sits in the
                             root on purpose, so the one manual task is visible
    <slug>/source/           input: video and transcript
    <slug>/decisions/        what the manager and the model decided
    <slug>/briefs/           reading packets, regenerable
    <slug>/publish/          what goes live
"""
from __future__ import annotations

import os

SOURCE = "source"
DECISIONS = "decisions"
BRIEFS = "briefs"
PUBLISH = "publish"


def ensure_dir(path: str) -> str:
    """Creates the file's folder if needed. Returns the path itself."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def episode(pd: str) -> str:
    return os.path.join(pd, "episode.json")


def video(pd: str) -> str:
    return os.path.join(pd, SOURCE, "video.mp4")


def transcript(pd: str) -> str:
    return os.path.join(pd, SOURCE, "transcript.json")


def transcript_txt(pd: str) -> str:
    return os.path.join(pd, SOURCE, "transcript.txt")


def source_dir(pd: str) -> str:
    return os.path.join(pd, SOURCE)


def curation(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "curation.json")


def moments(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "moments.json")


def texts(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "texts.json")


def posts(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "posts.json")


def schedule(pd: str) -> str:
    """Publishing schedule: which piece goes out on which day. Editorial."""
    return os.path.join(pd, DECISIONS, "schedule.json")


def published(pd: str) -> str:
    """Record of what already went live — the lock against a duplicate post."""
    return os.path.join(pd, DECISIONS, "published.json")


def brief(pd: str, kind: str) -> str:
    """kind: 'materials' | 'clips' | 'posts'."""
    return os.path.join(pd, BRIEFS, f"{kind}.md")


def thumbnail(pd: str) -> str:
    return os.path.join(pd, PUBLISH, "thumbnail.jpg")


def end_card_mp4(pd: str) -> str:
    """Cached end card — identical across every clip of the episode.

    Sits in the root of `publish/`, like the thumbnail: an episode artefact,
    not a per-piece one, and never committed (all of `projects/` is git-ignored).
    """
    return os.path.join(pd, PUBLISH, "_end_card.mp4")


def episode_txt(pd: str) -> str:
    """Episode title and description, ready to paste into YouTube.

    Sits in the root of `publish/`, next to the thumbnail: both belong to the
    whole episode, not to one piece — hence not inside a platform folder.
    """
    return os.path.join(pd, PUBLISH, "episode.txt")


def platform(pd: str, name: str) -> str:
    """Output folder for a video platform (youtube_shorts, ...)."""
    return os.path.join(pd, PUBLISH, name)


def posts_png(pd: str) -> str:
    return os.path.join(pd, PUBLISH, "instagram_posts")


# Old position -> new. The prefix in the old name was needed while everything
# sat in the same folder; inside the subfolder it becomes redundant.
#
# Retained for its SHAPE only. The keys are the pre-subfolder positions under
# current names, and no directory has ever held that combination: the layout
# that was flat held Portuguese names, and Phase 1 translated these keys rather
# than preserving them, because no `projects/` existed on disk to migrate. So
# the table is untested against real legacy data and can only match a fixture
# that recreates it. `migrate` stays wired into every command for the
# `_check_dirs` refusal and the duplicate-to-.bak handling, both of which apply
# to a project the pipeline itself half-wrote.
_MIGRATION = [
    ("source.mp4", video),
    ("transcript.json", transcript),
    ("transcript.txt", transcript_txt),
    ("curation.json", curation),
    ("moments.json", moments),
    ("texts.json", texts),
    ("posts.json", posts),
    ("brief_materials.md", lambda pd: brief(pd, "materials")),
    ("brief_clips.md", lambda pd: brief(pd, "clips")),
    ("brief_posts.md", lambda pd: brief(pd, "posts")),
    ("thumbnail.jpg", thumbnail),
]

# Output folders that only move, without the contents being renamed.
# Folder name for each platform. Named because they are more than directories:
# `render` uses them to tell which caption gets the episode call-to-action (the
# YouTube one), since both mp4s are identical and only the directory differs.
YOUTUBE_SHORTS = "youtube_shorts"
INSTAGRAM_REELS = "instagram_reels"
INSTAGRAM_POSTS = "instagram_posts"

_PUBLISH_DIRS = (YOUTUBE_SHORTS, INSTAGRAM_REELS, INSTAGRAM_POSTS)

# Temporary files that leaked into the root in earlier versions.
_JUNK = ("_thumb_frame.jpg",)


def _check_dirs(pd: str) -> None:
    """Refuses to migrate if a folder name is taken by a file.

    Without this `shutil.move` blows up halfway with a raw FileExistsError,
    which does not tell the manager what he has to sort out — and leaves the
    project half migrated.
    """
    for name in (SOURCE, DECISIONS, BRIEFS, PUBLISH):
        path = os.path.join(pd, name)
        if os.path.exists(path) and not os.path.isdir(path):
            raise RuntimeError(
                f"'{name}' must be a folder, but it is a file in {pd}. "
                f"Rename or remove that file and run again."
            )


def migrate(pd: str) -> list:
    """Moves a project from the old (everything loose) structure to the new one.

    Idempotent: runs at the start of every command and does nothing when the
    project is already organised. Returns the list of (origin, destination) moved.

    When the file exists in BOTH positions, the new one wins — it is what the
    commands have been writing since the migration. The old one is NOT deleted:
    it becomes `.bak` and enters the report. The manager may have copied a
    backup into the root on purpose, and silently deleting his work would be
    worse than leaving a spare file behind.

    Moves item by item, with no intermediate state: an interruption partway
    leaves the project partially migrated, and running again finishes the job.
    """
    import shutil

    if not os.path.isdir(pd):
        return []

    _check_dirs(pd)
    moved = []

    for old, dest_fn in _MIGRATION:
        origin = os.path.join(pd, old)
        if not os.path.exists(origin):
            continue
        destination = dest_fn(pd)
        if os.path.exists(destination):
            bak = origin + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
            os.rename(origin, bak)
            note = "(duplicate)"
            # Flag when the discarded file is bigger than the active one: the
            # new position may hold a half-written file (interrupted write) that
            # would silently take over. Size decides nothing — a smaller JSON is
            # normal — but the manager needs to see it to check.
            try:
                if os.path.getsize(bak) > os.path.getsize(destination):
                    note = "(duplicate — the .bak is BIGGER, check which counts)"
            except OSError:
                pass
            moved.append((old, os.path.basename(bak) + " " + note))
            continue
        ensure_dir(destination)
        shutil.move(origin, destination)
        moved.append((old, os.path.relpath(destination, pd)))

    for name in _PUBLISH_DIRS:
        origin = os.path.join(pd, name)
        if not os.path.isdir(origin):
            continue
        destination = os.path.join(pd, PUBLISH, name)

        if not os.path.isdir(destination):
            os.makedirs(os.path.join(pd, PUBLISH), exist_ok=True)
            shutil.move(origin, destination)
            moved.append((name + "/", os.path.relpath(destination, pd) + "/"))
            continue

        # Both exist: bring over what is only in the old one and remove it.
        # Skipping would leave an already-rendered clip outside the documented
        # structure, unannounced — and it would vanish at the next cleanup.
        for file in sorted(os.listdir(origin)):
            target = os.path.join(destination, file)
            current = os.path.join(origin, file)
            if os.path.exists(target):
                # The new position wins; the old becomes .bak beside it, for the
                # same reason as the loose files: never destroy silently.
                bak = target + ".bak"
                if os.path.exists(bak):
                    os.remove(bak)
                shutil.move(current, bak)
                moved.append((f"{name}/{file}",
                                os.path.relpath(bak, pd) + " (duplicate)"))
                continue
            shutil.move(current, target)
            moved.append((f"{name}/{file}", os.path.relpath(target, pd)))
        if not os.listdir(origin):
            os.rmdir(origin)

    for name in _JUNK:
        path = os.path.join(pd, name)
        if os.path.exists(path):
            os.remove(path)
            moved.append((name, "(removed)"))

    return moved

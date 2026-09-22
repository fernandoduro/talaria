"""Tests for the publishing schedule (schedule.json)."""
import datetime as dt
import json
import os
import tempfile
import unittest

from talaria import schedule, layout, published


def _prepare(pd, moments=None, posts=None, items=None):
    """Writes the sources and the schedule of a test project."""
    if moments is not None:
        with open(layout.ensure_dir(layout.moments(pd)), "w", encoding="utf-8") as f:
            json.dump(moments, f)
    if posts is not None:
        with open(layout.ensure_dir(layout.posts(pd)), "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f)
    if items is not None:
        with open(layout.ensure_dir(layout.schedule(pd)), "w", encoding="utf-8") as f:
            json.dump({"schedule": items}, f)


MOMENTS = [{"slug": "clip1", "start": 1.0, "end": 70.0, "title": "T"}]
POSTS = [{"slug": "quote_x", "cards": ["quote"], "caption": "cap"}]


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_a_valid_schedule_passes(self):
        _prepare(self.pd, MOMENTS, POSTS, [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-25", "kind": "post", "slug": "quote_x"},
        ])
        items = schedule.load(self.pd)
        self.assertEqual(len(items), 2)

    def test_a_missing_file_explains_what_to_create(self):
        with self.assertRaises(FileNotFoundError):
            schedule.load(self.pd)

    def test_a_nonexistent_clip_slug_aborts(self):
        # Publishing the wrong clip from a mistyped slug has no fix.
        _prepare(self.pd, MOMENTS, POSTS,
                 [{"date": "2026-08-24", "kind": "clip", "slug": "clip99"}])
        with self.assertRaises(ValueError) as ctx:
            schedule.load(self.pd)
        self.assertIn("clip99", str(ctx.exception))

    def test_a_nonexistent_post_slug_aborts(self):
        _prepare(self.pd, MOMENTS, POSTS,
                 [{"date": "2026-08-24", "kind": "post", "slug": "does_not_exist"}])
        with self.assertRaises(ValueError):
            schedule.load(self.pd)

    def test_an_impossible_date_aborts(self):
        # Validates the REAL date, not just the format — 30 February passes a
        # regex and would never publish.
        _prepare(self.pd, MOMENTS, POSTS,
                 [{"date": "2026-02-30", "kind": "clip", "slug": "clip1"}])
        with self.assertRaises(ValueError) as ctx:
            schedule.load(self.pd)
        self.assertIn("2026-02-30", str(ctx.exception))

    def test_a_wrong_date_format_aborts(self):
        _prepare(self.pd, MOMENTS, POSTS,
                 [{"date": "24/08/2026", "kind": "clip", "slug": "clip1"}])
        with self.assertRaises(ValueError):
            schedule.load(self.pd)

    def test_a_duplicate_slug_aborts(self):
        # Rescheduling means editing the item's date, not repeating the slug.
        _prepare(self.pd, MOMENTS, POSTS, [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-26", "kind": "clip", "slug": "clip1"},
        ])
        with self.assertRaises(ValueError) as ctx:
            schedule.load(self.pd)
        self.assertIn("appears twice", str(ctx.exception))

    def test_clip_and_post_sharing_a_slug_is_allowed(self):
        # A quote post inherits the slug of the clip it quotes; scheduling both
        # is not a repetition — they are distinct pieces, on distinct platforms.
        posts = [{"slug": "clip1", "cards": ["quote"], "caption": "cap"}]
        _prepare(self.pd, MOMENTS, posts, [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-25", "kind": "post", "slug": "clip1"},
        ])
        self.assertEqual(len(schedule.load(self.pd)), 2)

    def test_two_items_on_the_same_day_is_allowed(self):
        _prepare(self.pd, MOMENTS, POSTS, [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-24", "kind": "post", "slug": "quote_x"},
        ])
        self.assertEqual(len(schedule.load(self.pd)), 2)

    def test_an_unknown_kind_aborts(self):
        _prepare(self.pd, MOMENTS, POSTS,
                 [{"date": "2026-08-24", "kind": "reels", "slug": "clip1"}])
        with self.assertRaises(ValueError):
            schedule.load(self.pd)

    def test_a_slug_escaping_the_folder_aborts(self):
        # The slug becomes a filename in publish/. With a slash or a `..` it
        # leaves the episode folder: publish would find an mp4 from outside the
        # project, pass the pre-check and publish the wrong piece — with the
        # outside text becoming a public description.
        bad = "../../../other/clip"
        _prepare(self.pd,
                 [{"slug": bad, "start": 1.0, "end": 70.0, "title": "T"}],
                 POSTS,
                 [{"date": "2026-08-24", "kind": "clip", "slug": bad}])
        with self.assertRaises(ValueError) as ctx:
            schedule.load(self.pd)
        self.assertIn("cannot carry a slash", str(ctx.exception))

    def test_a_slug_with_a_single_slash_also_aborts(self):
        bad = "folder/clip"
        _prepare(self.pd,
                 [{"slug": bad, "start": 1.0, "end": 70.0, "title": "T"}],
                 POSTS,
                 [{"date": "2026-08-24", "kind": "clip", "slug": bad}])
        with self.assertRaises(ValueError):
            schedule.load(self.pd)

    def test_an_ordinary_slug_with_a_dot_still_works(self):
        # Sanitising must not get too strict: dots and hyphens are common in a
        # clip slug ("clip1_main-street.v2") and escape no folder.
        ok = "clip1_main-street.v2"
        _prepare(self.pd,
                 [{"slug": ok, "start": 1.0, "end": 70.0, "title": "T"}],
                 POSTS,
                 [{"date": "2026-08-24", "kind": "clip", "slug": ok}])
        self.assertEqual(len(schedule.load(self.pd)), 1)

    def test_a_carousel_over_10_aborts(self):
        # The Graph API limit is 10 images; the fix is editorial.
        posts = [{"slug": "long", "cards": ["c"] * 11, "caption": "x"}]
        _prepare(self.pd, MOMENTS, posts,
                 [{"date": "2026-08-24", "kind": "post", "slug": "long"}])
        with self.assertRaises(ValueError) as ctx:
            schedule.load(self.pd)
        self.assertIn("carousel accepts at most", str(ctx.exception))


class TestPending(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _prepare(self.pd, MOMENTS, POSTS, [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-25", "kind": "post", "slug": "quote_x"},
        ])

    def test_a_pending_clip_counts_for_two_platforms(self):
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual([(i["slug"], pl) for i, pl in pairs],
                         [("clip1", "youtube_shorts"),
                          ("clip1", "instagram_reels")])

    def test_the_future_does_not_enter(self):
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 23))
        self.assertEqual(pairs, [])

    def test_an_overdue_item_stays_pending(self):
        # Forgetting to run yesterday does not lose the publication.
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 30))
        self.assertEqual(len(pairs), 3)  # clip (2 platforms) + post

    def test_half_published_retries_only_what_was_missing(self):
        # YouTube went through, Instagram failed -> tomorrow only Instagram.
        published.record(self.pd, "youtube_shorts", "clip1", "a", "u")
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual([(i["slug"], pl) for i, pl in pairs],
                         [("clip1", "instagram_reels")])

    def test_everything_published_returns_empty(self):
        published.record(self.pd, "youtube_shorts", "clip1", "a", "u")
        published.record(self.pd, "instagram_reels", "clip1", "b", "u")
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual(pairs, [])

    def test_only_ignores_the_date_but_not_the_lock(self):
        # Bringing forward with --only works; republishing via --only does NOT.
        published.record(self.pd, "instagram_posts", "quote_x", "c", "u")
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 1),
                                    only=["clip1", "quote_x"])
        self.assertEqual([(i["slug"], pl) for i, pl in pairs],
                         [("clip1", "youtube_shorts"),
                          ("clip1", "instagram_reels")])

    def test_an_empty_only_does_not_become_the_whole_day(self):
        # `only=[]` means "filter to nothing", not "no filter": a caller that
        # composes the list from an empty flag would ask for the whole schedule
        # unintentionally, and publish the whole day believing it asked for one slug.
        self.assertEqual(
            schedule.pending(self.pd, day=dt.date(2026, 8, 30), only=[]), [])

    def test_platforms_restricts_what_goes_out(self):
        # While Instagram is not configured the whole clip would stall: the
        # pre-check demands credentials for BOTH platforms. Restricting lets
        # YouTube go out and keeps the Reel pending.
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24),
                                    platforms=["youtube_shorts"])
        self.assertEqual([(i["slug"], pl) for i, pl in pairs],
                         [("clip1", "youtube_shorts")])

    def test_a_restricted_platform_does_not_mark_the_other_as_published(self):
        # What did not go out stays pending — the lock is per (slug, platform).
        published.record(self.pd, "youtube_shorts", "clip1", "a", "u")
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual([pl for _, pl in pairs], ["instagram_reels"])

    def test_an_unknown_platform_aborts(self):
        with self.assertRaises(ValueError) as ctx:
            schedule.pending(self.pd, day=dt.date(2026, 8, 24),
                                platforms=["tiktok"])
        self.assertIn("tiktok", str(ctx.exception))

    def test_only_with_a_slug_off_the_schedule_aborts(self):
        with self.assertRaises(ValueError) as ctx:
            schedule.pending(self.pd, day=dt.date(2026, 8, 24),
                                only=["not_scheduled"])
        self.assertIn("not_scheduled", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

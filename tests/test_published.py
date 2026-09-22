"""Tests for the publication record (the lock against duplicate posts)."""
import json
import os
import tempfile
import unittest

from talaria import layout, published


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_no_file_returns_empty(self):
        # A project that never published: empty record, no error.
        self.assertEqual(published.load(self.pd), {})

    def test_corrupt_file_aborts_fail_closed(self):
        # Invalid JSON NEVER becomes "nothing published" — it would republish all.
        path = layout.ensure_dir(layout.published(self.pd))
        with open(path, "w", encoding="utf-8") as f:
            f.write("{metade de um json")
        with self.assertRaises(RuntimeError) as ctx:
            published.load(self.pd)
        self.assertIn("corrompido", str(ctx.exception))


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_writes_immediately_and_reads_back(self):
        published.record(self.pd, "youtube_shorts", "corte1", "abc123",
                           "https://youtube.com/shorts/abc123")
        reg = published.load(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        r = reg["youtube_shorts"][0]
        self.assertEqual(r["slug"], "corte1")
        self.assertEqual(r["id"], "abc123")
        self.assertIn("published_at", r)

    def test_accumulates_without_losing_the_earlier_ones(self):
        published.record(self.pd, "youtube_shorts", "corte1", "a", "u1")
        published.record(self.pd, "instagram_reels", "corte1", "b", "u2")
        reg = published.load(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        self.assertEqual(len(reg["instagram_reels"]), 1)

    def test_atomic_write_leaves_no_tmp(self):
        # temp + os.replace: either the whole new file, or the old one intact.
        published.record(self.pd, "instagram_posts", "post_x", "c", "u3")
        folder = os.path.dirname(layout.published(self.pd))
        leftovers = [n for n in os.listdir(folder) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestAlreadyPublished(unittest.TestCase):
    def test_finds_by_platform_and_slug(self):
        reg = {"youtube_shorts": [{"slug": "corte1", "id": "a"}]}
        self.assertTrue(published.is_published(reg, "youtube_shorts", "corte1"))
        # Same piece, different platform: does NOT count — the pending unit is
        # (slug, platform). A half-published clip retries only what was missing.
        self.assertFalse(published.is_published(reg, "instagram_reels", "corte1"))
        self.assertFalse(published.is_published(reg, "youtube_shorts", "corte2"))
        self.assertFalse(published.is_published({}, "youtube_shorts", "corte1"))


if __name__ == "__main__":
    unittest.main()

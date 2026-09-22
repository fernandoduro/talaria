"""Tests for reading texts.json into the thumbnail."""
import inspect
import json
import os
import tempfile
import unittest

from talaria import layout, texts, thumbnail


class TestTexts(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "episode.json"), "w", encoding="utf-8") as f:
            json.dump({
                "season": 2, "episode": 7, "company": "Zarvik",
                "city": "Fairbrook", "uf": "SP",
                "guests": [{"name": "Teresa", "role": "partner", "linkedin": ""}],
            }, f)

    def test_thumb_args_from_the_episode(self):
        args = texts.thumb_args(self.d)
        self.assertEqual(args["l1"], "Zarvik")
        self.assertEqual(args["l2"], "T2E07")
        self.assertIn("Fairbrook", args["subtitle"])
        self.assertIn("Teresa", args["credits"])

    def test_texts_json_overrides_the_episode(self):
        with open(layout.ensure_dir(layout.texts(self.d)), "w", encoding="utf-8") as f:
            json.dump({"thumb": {"l1": "CUSTOMISED", "l2": "T2E07"}}, f)
        args = texts.thumb_args(self.d)
        self.assertEqual(args["l1"], "CUSTOMISED")

    def test_badge_has_the_episode_code(self):
        args = texts.thumb_args(self.d)
        self.assertIn("T2E07", args["badge"])

    def test_save_and_read(self):
        texts.save(self.d, {"title": "X", "description": "Y"})
        t = texts.load(self.d)
        self.assertEqual(t["title"], "X")

    def test_load_without_a_file_returns_empty(self):
        self.assertEqual(texts.load(tempfile.mkdtemp()), {})

    def test_l1_falls_back_to_the_topic_without_a_company(self):
        """With no external guest, line 1 takes the episode topic."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "episode.json"), "w", encoding="utf-8") as f:
            json.dump({
                "season": 3, "episode": 1, "company": "",
                "city": "Stoneridge", "uf": "SP", "guests": [],
                "topics": ["the local startup ecosystem", "another"],
            }, f)
        args = texts.thumb_args(d)
        self.assertEqual(args["l1"], "the local startup ecosystem")

    def test_build_kwargs_matches_the_thumbnail_signature(self):
        """Translates l1/l2 -> headline_l1/headline_l2 without dropping a field."""
        kwargs = texts.build_kwargs(self.d)
        sig = inspect.signature(thumbnail.build_thumbnail)
        expected = {n for n, p in sig.parameters.items()
                     if p.kind is inspect.Parameter.KEYWORD_ONLY}
        self.assertEqual(set(kwargs), expected)

    def test_build_kwargs_translates_the_values(self):
        kwargs = texts.build_kwargs(self.d)
        self.assertEqual(kwargs["headline_l1"], "Zarvik")
        self.assertEqual(kwargs["headline_l2"], "T2E07")
        self.assertIn("Teresa", kwargs["credits"])


if __name__ == "__main__":
    unittest.main()

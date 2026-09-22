"""Tests for reading and validating episode.json."""
import json
import os
import tempfile
import unittest

from talaria import episode


class TestEpisode(unittest.TestCase):
    def _write(self, data):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "episode.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return d

    def test_reads_a_valid_episode(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Fairbrook", "uf": "SP",
            "guests": [{"name": "Teresa", "role": "CTO", "linkedin": "https://x"}],
        })
        ep = episode.load(d)
        self.assertEqual(ep["company"], "Zarvik")

    def test_code_has_two_digits(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Fairbrook", "uf": "SP", "guests": [],
        })
        ep = episode.load(d)
        self.assertEqual(episode.code(ep), "T2E07")

    def test_code_does_not_truncate_a_large_episode(self):
        d = self._write({
            "season": 2, "episode": 12, "company": "X",
            "city": "Stoneridge", "uf": "SP", "guests": [],
        })
        self.assertEqual(episode.code(episode.load(d)), "T2E12")

    def test_missing_field_gives_a_clear_error(self):
        d = self._write({"season": 2})
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        for field in ("company", "city", "uf", "guests"):
            self.assertIn(field, msg)
        self.assertNotIn("season", msg)   # present, must not be listed

    def test_missing_file_gives_a_clear_error(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            episode.load(d)

    def test_template_has_every_field(self):
        t = episode.template()
        for field in episode.REQUIRED_FIELDS:
            self.assertIn(field, t)

    def test_required_fields_do_not_shrink(self):
        self.assertEqual(
            set(episode.REQUIRED_FIELDS),
            {"season", "episode", "company", "city", "uf", "guests"},
        )

    def test_save_load_roundtrip_preserves_non_ascii(self):
        # The non-ASCII city IS the property: with ensure_ascii=True the file
        # would hold \\u0144 and this assertion would fail.
        d = tempfile.mkdtemp()
        data = {"season": 2, "episode": 7, "company": "Zarvik",
                 "city": "Gdańsk", "uf": "SP", "guests": []}
        path = episode.save(d, data)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertIn("Gdańsk", f.read())
        self.assertEqual(episode.load(d), data)

    def test_blank_template_is_refused(self):
        d = tempfile.mkdtemp()
        episode.save(d, episode.template())
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        # "blank fields" alone appears in the company-only message too, so the
        # field list is what says the general branch fired.
        self.assertIn("blank fields: season, episode, city", str(ctx.exception))

    def test_zero_counts_as_not_filled_in(self):
        """There is no season 0 or episode 0 — the template seeds both with 0."""
        d = self._write({
            "season": 0, "episode": 0, "company": "Zarvik",
            "city": "Stoneridge", "uf": "SP", "guests": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        self.assertIn("blank fields", msg)
        self.assertIn("season", msg)
        self.assertIn("episode", msg)

    def test_empty_guests_is_accepted(self):
        """A hosts-only episode is a real case from the materials prompt."""
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Stoneridge", "uf": "SP", "guests": [],
        })
        self.assertEqual(episode.load(d)["guests"], [])

    def test_wrong_type_gives_a_clear_error(self):
        d = self._write({
            "season": "two", "episode": 7, "company": "Zarvik",
            "city": "Stoneridge", "uf": "SP", "guests": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        self.assertIn("season", msg)
        self.assertIn("whole number", msg)

    def test_hosts_only_episode_is_accepted(self):
        """With no external guest, `company` may be empty."""
        d = self._write({
            "season": 3, "episode": 1, "company": "",
            "city": "Stoneridge", "uf": "SP", "guests": [],
            "topics": ["the local startup ecosystem"],
        })
        ep = episode.load(d)
        self.assertEqual(ep["company"], "")

    def test_no_guest_and_no_topic_is_refused(self):
        """With no company, the topic sources thumbnail line 1 and the hashtag."""
        d = self._write({
            "season": 3, "episode": 1, "company": "",
            "city": "Stoneridge", "uf": "SP", "guests": [], "topics": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        self.assertIn("topic", str(ctx.exception).lower())

    def test_with_a_guest_company_stays_required(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "",
            "city": "Stoneridge", "uf": "SP",
            "guests": [{"name": "Teresa", "role": "partner", "linkedin": ""}],
        })
        with self.assertRaises(ValueError):
            episode.load(d)


if __name__ == "__main__":
    unittest.main()

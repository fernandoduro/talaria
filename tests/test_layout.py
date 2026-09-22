"""Tests for the project file layout."""
import os
import tempfile
import unittest

from talaria import layout


class TestPaths(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_episode_stays_at_the_root(self):
        self.assertEqual(layout.episode(self.d),
                         os.path.join(self.d, "episode.json"))

    def test_source_grouped(self):
        self.assertTrue(layout.video(self.d).endswith("source/video.mp4"))
        self.assertTrue(layout.transcript(self.d).endswith("source/transcript.json"))
        self.assertTrue(layout.transcript_txt(self.d).endswith("source/transcript.txt"))

    def test_decisions_grouped(self):
        for f in (layout.curation(self.d), layout.moments(self.d),
                  layout.texts(self.d), layout.posts(self.d)):
            self.assertIn("/decisions/", f)

    def test_briefs_by_kind(self):
        self.assertTrue(layout.brief(self.d, "clips").endswith("briefs/clips.md"))
        self.assertTrue(layout.brief(self.d, "posts").endswith("briefs/posts.md"))

    def test_publishables_grouped(self):
        self.assertTrue(layout.thumbnail(self.d).endswith("publish/thumbnail.jpg"))
        self.assertTrue(layout.platform(self.d, "youtube_shorts")
                        .endswith("publish/youtube_shorts"))
        self.assertTrue(layout.posts_png(self.d).endswith("publish/instagram_posts"))

    def test_ensure_dir_creates_the_files_folder(self):
        target = layout.ensure_dir(layout.moments(self.d))
        self.assertTrue(os.path.isdir(os.path.dirname(target)))


class TestMigration(unittest.TestCase):
    OLD_NAMES = ["source.mp4", "transcript.json", "transcript.txt",
               "curation.json", "moments.json", "texts.json", "posts.json",
               "brief_materials.md", "brief_clips.md", "brief_posts.md",
               "thumbnail.jpg", "_thumb_frame.jpg", "episode.json"]

    def _old_project(self):
        d = tempfile.mkdtemp()
        for name in self.OLD_NAMES:
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(name)
        for sub in ("youtube_shorts", "instagram_reels", "instagram_posts"):
            os.makedirs(os.path.join(d, sub))
            with open(os.path.join(d, sub, "x.mp4"), "w") as f:
                f.write("x")
        return d

    def test_moves_everything_to_the_right_place(self):
        d = self._old_project()
        moved = layout.migrate(d)
        self.assertGreater(len(moved), 0)
        self.assertTrue(os.path.exists(layout.video(d)))
        self.assertTrue(os.path.exists(layout.transcript(d)))
        self.assertTrue(os.path.exists(layout.moments(d)))
        self.assertTrue(os.path.exists(layout.brief(d, "clips")))
        self.assertTrue(os.path.exists(layout.thumbnail(d)))
        self.assertTrue(os.path.exists(
            os.path.join(layout.platform(d, "youtube_shorts"), "x.mp4")))

    def test_content_preserved(self):
        d = self._old_project()
        layout.migrate(d)
        with open(layout.moments(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "moments.json")

    def test_episode_json_stays_at_the_root(self):
        d = self._old_project()
        layout.migrate(d)
        self.assertTrue(os.path.exists(layout.episode(d)))
        self.assertEqual(os.path.dirname(layout.episode(d)), d)

    def test_temporary_junk_is_removed(self):
        d = self._old_project()
        layout.migrate(d)
        self.assertFalse(os.path.exists(os.path.join(d, "_thumb_frame.jpg")))

    def test_root_keeps_only_episode_and_the_folders(self):
        d = self._old_project()
        layout.migrate(d)
        at_root = {n for n in os.listdir(d) if not n.startswith(".")}
        self.assertEqual(at_root, {"episode.json", "source", "decisions",
                                   "briefs", "publish"})

    def test_is_idempotent(self):
        d = self._old_project()
        layout.migrate(d)
        self.assertEqual(layout.migrate(d), [])   # 2nd run moves nothing
        self.assertTrue(os.path.exists(layout.moments(d)))

    def test_new_project_is_untouched(self):
        d = tempfile.mkdtemp()
        self.assertEqual(layout.migrate(d), [])

    def test_does_not_overwrite_an_already_migrated_file(self):
        """If both exist, the NEW position wins — it is the most recent."""
        d = self._old_project()
        layout.migrate(d)
        with open(layout.moments(d), "w", encoding="utf-8") as f:
            f.write("NOVO")
        with open(os.path.join(d, "moments.json"), "w", encoding="utf-8") as f:
            f.write("ANTIGO")
        layout.migrate(d)
        with open(layout.moments(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "NOVO")
        # and the old one is preserved as .bak, not deleted
        with open(os.path.join(d, "moments.json.bak"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "ANTIGO")


class TestDefensiveMigration(unittest.TestCase):
    """Scenarios where the migration could lose or hide work."""

    def test_duplicate_is_not_deleted_silently(self):
        """File in both places: the new one wins, but the old becomes .bak.

        Real scenario: the manager copies a backup moments.json into the root
        to restore something. Without this, the next command would delete it
        without a word — and the migration report would come back empty.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.DECISIONS))
        with open(layout.moments(d), "w", encoding="utf-8") as f:
            f.write("NOVO")
        with open(os.path.join(d, "moments.json"), "w", encoding="utf-8") as f:
            f.write("ANTIGO")

        moved = layout.migrate(d)

        with open(layout.moments(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "NOVO")          # the new one still applies
        self.assertFalse(os.path.exists(os.path.join(d, "moments.json")))
        bak = os.path.join(d, "moments.json.bak")
        self.assertTrue(os.path.exists(bak))            # the old one did not vanish
        with open(bak, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ANTIGO")
        self.assertTrue(any("bak" in destination for _, destination in moved),
                        f"o relatório precisa mencionar o .bak: {moved}")

    def test_folder_name_taken_by_a_file_gives_a_useful_error(self):
        """A file named 'decisions' blocks the folder — the error must say so."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "moments.json"), "w", encoding="utf-8") as f:
            f.write("x")
        with open(os.path.join(d, layout.DECISIONS), "w", encoding="utf-8") as f:
            f.write("sou um arquivo, não uma pasta")

        with self.assertRaises(RuntimeError) as ctx:
            layout.migrate(d)
        msg = str(ctx.exception)
        self.assertIn(layout.DECISIONS, msg)
        self.assertIn("pasta", msg.lower())
        # nothing was lost: the original file is still where it was
        self.assertTrue(os.path.exists(os.path.join(d, "moments.json")))


    def test_warns_when_the_discarded_duplicate_is_bigger(self):
        """A half-written file in the new position cannot go unnoticed.

        Size does not decide which one counts (a smaller JSON is normal), but a
        15-byte video becoming the active one while the 2GB file becomes .bak
        has to jump out of the report.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.SOURCE))
        with open(layout.video(d), "w") as f:
            f.write("X" * 15)                     # stub in the new position
        with open(os.path.join(d, "source.mp4"), "w") as f:
            f.write("V" * 30000)                  # real video in the old one

        moved = layout.migrate(d)

        self.assertTrue(any("MAIOR" in destination for _, destination in moved),
                        f"o relatório precisa avisar: {moved}")

    def test_duplicate_output_folder_is_reported(self):
        """An old folder holding content the new one lacks cannot be orphaned.

        Without a warning, two already-rendered clips would sit outside the
        documented structure — and vanish at the next episode-folder cleanup.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.PUBLISH, "youtube_shorts"))
        with open(os.path.join(d, layout.PUBLISH, "youtube_shorts", "c1.mp4"), "w") as f:
            f.write("novo")
        os.makedirs(os.path.join(d, "youtube_shorts"))
        for n in ("c1.mp4", "c2.mp4"):
            with open(os.path.join(d, "youtube_shorts", n), "w") as f:
                f.write("antigo " + n)

        moved = layout.migrate(d)

        # what only existed in the old one was brought over
        destination = os.path.join(d, layout.PUBLISH, "youtube_shorts")
        self.assertTrue(os.path.exists(os.path.join(destination, "c2.mp4")))
        # what already existed in the new one was not overwritten
        with open(os.path.join(destination, "c1.mp4"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "novo")
        # and the report does not stay silent
        self.assertTrue(moved, "mover conteúdo órfão precisa aparecer no relatório")
        self.assertFalse(os.path.isdir(os.path.join(d, "youtube_shorts")))

    def test_interruption_is_recoverable(self):
        """Partial migration: running again finishes the job, losing nothing."""
        import shutil as _sh
        d = tempfile.mkdtemp()
        names = ("source.mp4", "moments.json", "curation.json", "texts.json",
                 "brief_clips.md", "thumbnail.jpg")
        for n in names:
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(n)

        original = _sh.move
        state = {"n": 0}

        def move_that_dies(a, b):
            state["n"] += 1
            if state["n"] == 3:
                raise KeyboardInterrupt("simula ctrl-c no meio")
            return original(a, b)

        _sh.move = move_that_dies
        try:
            with self.assertRaises(KeyboardInterrupt):
                layout.migrate(d)
        finally:
            _sh.move = original

        layout.migrate(d)                      # 2nd run completes it

        survivors = []
        for root, _, files in os.walk(d):
            survivors += files
        self.assertEqual(len(survivors), len(names))
        self.assertTrue(os.path.exists(layout.moments(d)))
        self.assertTrue(os.path.exists(layout.video(d)))


if __name__ == "__main__":
    unittest.main()


class TestEpisodeCaption(unittest.TestCase):
    def test_stays_at_the_publish_root(self):
        # Next to the thumbnail: both are artefacts of the whole episode,
        # not of one specific piece.
        d = tempfile.mkdtemp()
        self.assertEqual(layout.episode_txt(d),
                         os.path.join(d, "publish", "episode.txt"))


class TestPublishPaths(unittest.TestCase):
    def test_schedule_in_decisions(self):
        self.assertEqual(layout.schedule("/p/ep8"),
                         os.path.join("/p/ep8", "decisions", "schedule.json"))

    def test_published_in_decisions(self):
        self.assertEqual(layout.published("/p/ep8"),
                         os.path.join("/p/ep8", "decisions", "published.json"))

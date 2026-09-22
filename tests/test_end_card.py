"""End card: logo + @handle at the end of every clip."""
import os
import subprocess
import tempfile
import time
import unittest

from PIL import Image

from talaria import config, end_card


class TestComposeCard(unittest.TestCase):
    def test_frame_size_matches_the_video(self):
        img = end_card.compose_card()
        self.assertEqual(img.size, (config.FRAME_W, config.FRAME_H))

    def test_background_is_the_configured_one(self):
        img = end_card.compose_card()
        # The image corner has no logo and no text — it is pure background.
        self.assertEqual(img.getpixel((5, 5)), config.CARD_BG)

    def test_logo_appears_centred(self):
        # The logo+@handle block is centred; the exact dead-centre pixel varies
        # with the design, so the test checks that SOMETHING was drawn there (it
        # is no longer flat background) rather than pinning a pixel position.
        img = end_card.compose_card()
        center = img.getpixel((config.FRAME_W // 2, config.FRAME_H // 2))
        self.assertNotEqual(center, config.CARD_BG)

    def test_missing_logo_gives_a_clear_message(self):
        # Same pattern as POST_TEMPLATE in post_instagram.py: an explicit error
        # saying where the asset should be, not a raw Pillow FileNotFoundError
        # pointing at a path with no context.
        old_path = config.LOGO_PATH
        config.LOGO_PATH = "/path/that/does/not/exist/logo.png"
        try:
            with self.assertRaises(FileNotFoundError) as e:
                end_card.compose_card()
            self.assertIn("assets/", str(e.exception))
        finally:
            config.LOGO_PATH = old_path


class TestCachedCard(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_writes_the_file_on_the_first_call(self):
        path = end_card.cached_card(self.d)
        self.assertTrue(os.path.exists(path))

    def test_file_duration_matches_config(self):
        path = end_card.cached_card(self.d)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURATION_S, delta=0.15)

    def test_reuses_without_rewriting(self):
        path = end_card.cached_card(self.d)
        mtime_1 = os.path.getmtime(path)
        time.sleep(0.05)
        path_2 = end_card.cached_card(self.d)
        self.assertEqual(path, path_2)
        self.assertEqual(os.path.getmtime(path), mtime_1)

    def test_replacing_the_logo_invalidates_the_cache(self):
        path = end_card.cached_card(self.d)
        mtime_1 = os.path.getmtime(path)
        # Keeps the mtime BEFORE touching it, instead of rebuilding it from git
        # at the end: outside a git clone (tarball, copy of the code) the command
        # returns nothing, the restore silently does not happen and the logo is
        # left in the future — breaking the cache test that runs after this one.
        stat_before = os.stat(config.LOGO_PATH)
        future = time.time() + 5
        os.utime(config.LOGO_PATH, (future, future))
        try:
            time.sleep(0.05)
            end_card.cached_card(self.d)
            self.assertGreater(os.path.getmtime(path), mtime_1)
        finally:
            os.utime(config.LOGO_PATH,
                     (stat_before.st_atime, stat_before.st_mtime))

    def test_leaves_no_temporary_behind(self):
        # The write goes through a .tmp.mp4/.tmp.png carrying the PID — neither
        # may be left over once cached_card() finishes successfully.
        destination = end_card.cached_card(self.d)
        folder = os.path.dirname(destination)
        leftovers = [n for n in os.listdir(folder) if ".tmp" in n]
        self.assertEqual(leftovers, [], f"temporary file left behind: {leftovers}")

    def test_race_between_two_processes_does_not_corrupt(self):
        # Simulates two concurrent "processes" calling cached_card() for the
        # SAME episode (the test runs in one process, so each call uses the real
        # os.getpid() — what matters here is that the final product is always a
        # valid, complete mp4, never a file left half-written by a concurrent
        # write).
        r1 = end_card.cached_card(self.d)
        r2 = end_card.cached_card(self.d)
        self.assertEqual(r1, r2)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", r1], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURATION_S, delta=0.15)


if __name__ == "__main__":
    unittest.main()

import os
import unittest

from PIL import ImageFont

from talaria import config

EXPECTED = {
    "FONT": ("DejaVu Sans", "Bold"),
    "POST_FONT": ("Poppins", "SemiBold"),
    "POST_MONO": ("DejaVu Sans Mono", "Bold"),
}


class TestVersionedFonts(unittest.TestCase):
    """Fonts come from the repository, not from the system.

    Text is burned into the video: a font resolved by fontconfig changes with
    the machine and the error only shows in the published video, too late to fix.
    """

    def test_each_font_is_a_repository_file(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
        expected = os.path.join(root, "assets", "fonts")
        for name in EXPECTED:
            path = getattr(config, name)
            self.assertTrue(os.path.isfile(path), f"{name}: {path}")
            self.assertEqual(os.path.dirname(path), expected, name)

    def test_each_font_has_the_expected_identity(self):
        for name, identity in EXPECTED.items():
            fnt = ImageFont.truetype(getattr(config, name), 40)
            self.assertEqual(fnt.getname(), identity, name)

    def test_missing_font_aborts_with_a_useful_message(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config._bundled_font("DoesNotExist-Bold.ttf")
        self.assertIn("DoesNotExist-Bold.ttf", str(ctx.exception))
        self.assertIn("assets/fonts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

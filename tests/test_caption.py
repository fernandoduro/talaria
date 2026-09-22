"""Tests for the publishing caption (.txt beside each piece)."""
import contextlib
import io
import os
import tempfile
import unittest

from talaria import caption


class TestBuild(unittest.TestCase):
    def test_joins_description_and_hashtags(self):
        t = caption.compose("A frase do corte.", "#Um #Dois")
        self.assertEqual(t, "A frase do corte.\n\n#Um #Dois")

    def test_description_only_when_there_are_no_hashtags(self):
        # Without texts.json the episode has no hashtags; the caption still works.
        self.assertEqual(caption.compose("A frase.", ""), "A frase.")

    def test_hashtags_only_when_there_is_no_description(self):
        # Clip with no post_caption: the file comes out, with no leading blank line.
        self.assertEqual(caption.compose("", "#Um"), "#Um")

    def test_empty_on_both_sides(self):
        self.assertEqual(caption.compose("", ""), "")

    def test_none_treated_as_empty(self):
        # post_caption absent from the JSON arrives as None, not as "".
        self.assertEqual(caption.compose(None, None), "")
        self.assertEqual(caption.compose(None, "#Um"), "#Um")

    def test_trims_surrounding_space(self):
        self.assertEqual(caption.compose("  A frase.  ", " #Um "), "A frase.\n\n#Um")


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_swaps_the_pieces_extension(self):
        piece = os.path.join(self.d, "corte1_short.mp4")
        out = caption.write(piece, "texto")
        self.assertEqual(out, os.path.join(self.d, "corte1_short.txt"))
        self.assertTrue(os.path.exists(out))

    def test_content_written_as_utf8(self):
        piece = os.path.join(self.d, "post_x.png")
        caption.write(piece, "Ação e coração.\n\n#RibeiraoAcai")
        with open(os.path.join(self.d, "post_x.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Ação e coração.\n\n#RibeiraoAcai")

    def test_overwrites_without_duplicating(self):
        # Regenerating twice leaves a single file, with the new content.
        piece = os.path.join(self.d, "corte1_short.mp4")
        caption.write(piece, "primeira")
        caption.write(piece, "segunda")
        with open(os.path.join(self.d, "corte1_short.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "segunda")
        txts = [n for n in os.listdir(self.d) if n.endswith(".txt")]
        self.assertEqual(txts, ["corte1_short.txt"])

    def test_creates_the_missing_directory(self):
        piece = os.path.join(self.d, "sub", "nova", "corte1_short.mp4")
        out = caption.write(piece, "texto")
        self.assertTrue(os.path.exists(out))

    def test_carousel_base_name_comes_from_the_caller(self):
        # The carousel .txt uses the post slug, not the card name.
        # The caller passes the base path; write() only swaps the extension.
        base = os.path.join(self.d, "post_corte2.png")
        out = caption.write(base, "legenda do carrossel")
        self.assertTrue(out.endswith("post_corte2.txt"))



class TestValidateText(unittest.TestCase):
    """A wrong type in the JSON gives a named error, not a raw AttributeError.

    `compose()` is the single authority on the format, so validation lives here:
    render and post_instagram inherit the same message instead of each writing
    its own — which is how the two versions diverged in the first implementation.
    """

    def test_number_is_rejected_naming_the_field_and_the_piece(self):
        with self.assertRaises(ValueError) as e:
            caption.validate("legenda", 123, "corte1")
        msg = str(e.exception)
        self.assertIn("corte1", msg)
        self.assertIn("legenda", msg)
        self.assertIn("int", msg)

    def test_list_is_rejected(self):
        with self.assertRaises(ValueError) as e:
            caption.validate("post_caption", ["a"], "corte2")
        self.assertIn("list", str(e.exception))

    def test_text_and_none_pass(self):
        # None is an absent key in the JSON — normal, not an error.
        self.assertIsNone(caption.validate("legenda", "ok", "c1"))
        self.assertIsNone(caption.validate("legenda", None, "c1"))

class TestEmDash(unittest.TestCase):
    """The channel does not use em dashes in captions: it reads as AI text."""

    def _validate(self, value):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            caption.validate("post_caption", value, "corte1")
        return buf.getvalue()

    def test_warns_on_em_dash(self):
        output = self._validate("Ele avisou — e errou assim mesmo.")
        self.assertIn("travessão", output)
        self.assertIn("corte1", output)

    def test_no_warning_without_an_em_dash(self):
        self.assertEqual(self._validate("Ele avisou. E errou assim mesmo."), "")

    def test_hyphen_and_en_dash_do_not_trigger(self):
        # A compound-word hyphen and a range en dash are legitimate
        # punctuation; only the em dash (—) is the construction rejected here.
        self.assertEqual(self._validate("e-mail, 30–40 minutos"), "")

    def test_em_dash_does_not_abort(self):
        # A matter of style: warn and let it through. Aborting would block a
        # whole render over one character.
        caption.validate("post_caption", "Com — travessão", "corte1")


class TestComposeEpisode(unittest.TestCase):
    """Caption for the whole episode: title on line 1, then the description."""

    def test_title_description_and_hashtags(self):
        t = caption.compose_episode("O Título", "A descrição.", "#Um")
        self.assertEqual(t, "O Título\n\nA descrição.\n\n#Um")

    def test_no_title_leaves_no_stray_line(self):
        self.assertEqual(caption.compose_episode("", "A descrição.", "#Um"),
                         "A descrição.\n\n#Um")

    def test_title_only(self):
        self.assertEqual(caption.compose_episode("O Título", "", ""), "O Título")

    def test_none_in_any_field(self):
        self.assertEqual(caption.compose_episode(None, None, None), "")

    def test_description_keeps_its_own_breaks(self):
        # The YouTube description has blocks and separators; do not flatten it.
        desc = "Linha 1\n\n---\n\nLinha 2"
        t = caption.compose_episode("T", desc, "#Um")
        self.assertIn("---", t)
        self.assertTrue(t.startswith("T\n\nLinha 1"))


if __name__ == "__main__":
    unittest.main()

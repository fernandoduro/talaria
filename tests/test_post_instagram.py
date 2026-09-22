"""Tests for the Instagram quote post."""
import json
import os
import tempfile
import unittest

from talaria import config, layout, post_instagram


class TestConfigPost(unittest.TestCase):
    def test_template_exists_in_the_repo(self):
        self.assertTrue(os.path.exists(config.POST_TEMPLATE),
                        f"template not found at {config.POST_TEMPLATE}")

    def test_measurements_match_the_template(self):
        from PIL import Image
        with Image.open(config.POST_TEMPLATE) as im:
            self.assertEqual(im.size, (config.POST_W, config.POST_H))

    def test_quote_does_not_invade_the_rule(self):
        # 5 lines fit; a 6th would invade the rule at y=2242.
        end_5 = config.POST_QUOTE_Y + 4 * config.POST_QUOTE_STEP + config.POST_QUOTE_LINE_H
        end_6 = config.POST_QUOTE_Y + 5 * config.POST_QUOTE_STEP + config.POST_QUOTE_LINE_H
        self.assertLess(end_5, config.POST_RULE_Y)
        self.assertGreater(end_6, config.POST_RULE_Y)


class TestFit(unittest.TestCase):
    def test_design_quote_fits_in_5_lines(self):
        txt = ("Everybody told us we had to move to a bigger city. We "
               "stayed, and that turned out to be the edge.")
        r = post_instagram.validate_card(txt)
        self.assertTrue(r["fits"])
        self.assertEqual(r["lines"], 5)

    def test_short_quote_fits(self):
        r = post_instagram.validate_card("The blue ocean was right there.")
        self.assertTrue(r["fits"])
        self.assertLessEqual(r["lines"], 5)

    def test_long_quote_is_rejected_with_the_excess(self):
        txt = ("Sometimes the opportunity is right beside you and you are "
               "so focused on one thing that you never look sideways at it.")
        r = post_instagram.validate_card(txt)
        self.assertFalse(r["fits"])
        self.assertGreater(r["lines"], 5)
        # The line-count branch, not the word "line": the width refusal also
        # quotes a line, so the bare word would stop discriminating.
        self.assertIn("more than the limit of", r["reason"])

    def test_empty_text_is_rejected(self):
        r = post_instagram.validate_card("   ")
        self.assertFalse(r["fits"])

    def test_word_wider_than_the_card_is_rejected(self):
        """A word with nowhere to break comes out cut off — refuse, not write.

        The line count misses this case: the word occupies ONE line and passes
        the limit of 5, but overflows the width.
        'pneumonoultramicroscopicsilicovolcanoconiosis' already overflows, and
        a URL or compound name gets there easily.
        """
        r = post_instagram.validate_card(
            "pneumonoultramicroscopicsilicovolcanoconiosis")
        self.assertFalse(r["fits"])
        self.assertEqual(r["lines"], 1)      # the line count would have passed
        self.assertIn("does not fit the card width", r["reason"])

    def test_sentence_with_a_long_ordinary_word_still_fits(self):
        """The refusal is by measurement, not by word length in characters."""
        r = post_instagram.validate_card(
            "Internationalisation and restructuring.")
        self.assertTrue(r["fits"])
        self.assertEqual(r["lines"], 2)


class TestRender(unittest.TestCase):
    def test_produces_a_png_at_the_template_size(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            post_instagram.render_card(
                "The blue ocean was right there.",
                {"name": "Marina Vance", "role": "Partner", "company": "Zarvik"},
                out,
            )
            self.assertTrue(os.path.exists(out))
            with Image.open(out) as im:
                self.assertEqual(im.size, (config.POST_W, config.POST_H))

    def test_a_card_that_does_not_fit_raises(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(ValueError) as ctx:
                post_instagram.render_card(
                    "Sometimes the opportunity is right beside you and you "
                    "are so focused on one thing that you never look "
                    "sideways at it.",
                    {"name": "X", "role": "Y", "company": "Z"},
                    out,
                )
            self.assertIn("lines", str(ctx.exception))
            self.assertFalse(os.path.exists(out))

    def test_missing_template_gives_a_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(FileNotFoundError) as ctx:
                post_instagram.render_card(
                    "Short.", {"name": "X", "role": "Y", "company": "Z"},
                    out, template=os.path.join(d, "does-not-exist.png"),
                )
            self.assertIn("template", str(ctx.exception).lower())


def _fake_project(d):
    """Creates a minimal project with episode.json filled in."""
    ep = {
        "season": 2, "episode": 8, "company": "Zarvik",
        "city": "Fairbrook", "uf": "SP",
        "guests": [{"name": "Marina Vance", "role": "Partner",
                        "linkedin": "https://example"}],
        "topics": [],
    }
    with open(layout.ensure_dir(layout.episode(d)), "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False)
    return d


class TestAuthorAndText(unittest.TestCase):
    def test_author_comes_from_episode_json(self):
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            a = post_instagram.episode_author(d)
            self.assertEqual(a["name"], "Marina Vance")
            self.assertEqual(a["role"], "Partner")
            self.assertEqual(a["company"], "Zarvik")

    def test_episode_without_a_guest_uses_the_company(self):
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            with open(os.path.join(d, "episode.json"), encoding="utf-8") as f:
                ep = json.load(f)
            ep["guests"] = []
            with open(os.path.join(d, "episode.json"), "w", encoding="utf-8") as f:
                json.dump(ep, f, ensure_ascii=False)
            a = post_instagram.episode_author(d)
            self.assertEqual(a["name"], "Zarvik")
            self.assertEqual(a["role"], "")

    def test_two_guests_allow_choosing_who_signs(self):
        """The 2nd guest's quote must not come out under the 1st one's name.

        Attributing the sentence to the wrong person is the worst error of this
        step — the post prints name and role beneath the quote marks.
        """
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            with open(os.path.join(d, "episode.json"), encoding="utf-8") as f:
                ep = json.load(f)
            ep["guests"].append({"name": "Rafael Nunes", "role": "CEO"})
            with open(os.path.join(d, "episode.json"), "w", encoding="utf-8") as f:
                json.dump(ep, f, ensure_ascii=False)

            default = post_instagram.episode_author(d)
            self.assertEqual(default["name"], "Marina Vance")

            second = post_instagram.episode_author(d, who="Rafael Nunes")
            self.assertEqual(second["name"], "Rafael Nunes")
            self.assertEqual(second["role"], "CEO")

    def test_unknown_author_errors_instead_of_misattributing(self):
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            with self.assertRaises(ValueError) as ctx:
                post_instagram.episode_author(d, who="Nobody Here")
            self.assertIn("Nobody Here", str(ctx.exception))
            self.assertIn("Marina Vance", str(ctx.exception))

    def test_spoken_only_forms_are_expanded(self):
        t = post_instagram.clean_quote("You gotta pick one problem", [])
        self.assertIn("got to", t)
        self.assertNotIn(" gotta ", f" {t} ")

    def test_company_name_is_corrected(self):
        t = post_instagram.clean_quote("Zarvic grew fast", ["Zarvik"])
        self.assertIn("Zarvik", t)
        self.assertNotIn("Zarvic", t)


class TestGenerate(unittest.TestCase):
    def _with_posts(self, d, posts):
        _fake_project(d)
        with open(layout.ensure_dir(layout.posts(d)), "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f, ensure_ascii=False)

    def test_single_card_produces_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "clip1_blue_ocean",
                                 "cards": ["The blue ocean was right there."]}])
            generated = post_instagram.generate(d)
            self.assertEqual(len(generated), 1)
            self.assertTrue(generated[0].endswith("post_clip1_blue_ocean.png"))
            self.assertTrue(os.path.exists(generated[0]))

    def test_carousel_produces_numbered_files_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "clip3_b2b", "cards": [
                "In B2B you deliver and it is over.",
                "The responsibility afterwards belongs to the other side.",
            ]}])
            generated = post_instagram.generate(d)
            self.assertEqual(len(generated), 2)
            self.assertTrue(generated[0].endswith("post_clip3_b2b_1.png"))
            self.assertTrue(generated[1].endswith("post_clip3_b2b_2.png"))

    def test_overflowing_card_aborts_without_writing_anything(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "ok", "cards": ["Short."]},
                                {"slug": "bad", "cards": [
                                    "Sometimes the opportunity is right "
                                    "beside you and you are so focused on "
                                    "one thing that you never look sideways "
                                    "at it."]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.generate(d)
            self.assertIn("bad", str(ctx.exception))
            # Fails before writing: no folder with half-finished material.
            self.assertFalse(os.path.exists(layout.posts_png(d)))

    def test_non_text_card_gives_a_useful_error(self):
        """posts.json is hand-written: a numeric card must not become an
        AttributeError coming out of the text cleanup."""
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "a", "cards": [123]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.generate(d)
            self.assertIn("expected text", str(ctx.exception))

    def test_slug_with_a_slash_does_not_escape_the_output_folder(self):
        """The slug is hand-typed in posts.json — it must not become a path.

        Without sanitising, `../outside` creates a junk directory and `../../..`
        breaks with an obscure Pillow FileNotFoundError instead of writing.
        """
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "../../outside", "cards": ["Short."]}])
            generated = post_instagram.generate(d)
            output = os.path.realpath(layout.posts_png(d))
            self.assertTrue(os.path.realpath(generated[0]).startswith(output + os.sep))
            self.assertNotIn("..", os.path.basename(generated[0]))

    def test_author_in_the_json_is_ignored_in_favour_of_the_episode(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "c1", "cards": ["Short."],
                                 "author": {"name": "Wrong Name",
                                           "role": "X", "company": "Y"}}])
            post_instagram.generate(d)
            # The PNG text cannot be read; the contract is the author function.
            self.assertEqual(post_instagram.episode_author(d)["name"],
                             "Marina Vance")


if __name__ == "__main__":
    unittest.main()


class TestPostCaption(unittest.TestCase):
    """The post's publishing .txt — one per post, not one per card."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_single_card_has_a_txt_named_with_the_slug(self):
        # Simple post -> post_<slug>.txt
        output = self.d
        written = post_instagram.write_captions(
            output, [("clip1", "The post caption.")], "#One #Two")
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].endswith("post_clip1.txt"))
        with open(written[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "The post caption.\n\n#One #Two")

    def test_carousel_produces_a_single_txt(self):
        # 2 cards, 1 caption. The main edge case of this feature.
        written = post_instagram.write_captions(
            self.d, [("clip2", "Carousel caption.")], "#One")
        self.assertEqual(len(written), 1)
        names = sorted(n for n in os.listdir(self.d) if n.endswith(".txt"))
        self.assertEqual(names, ["post_clip2.txt"])

    def test_missing_caption_warns_and_writes_hashtags(self):
        # Same contract as the clip — it does not vanish silently.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            post_instagram.write_captions(self.d, [("clip3", "")], "#One")
        self.assertIn("clip3", buf.getvalue())
        self.assertIn("no caption", buf.getvalue())
        with open(os.path.join(self.d, "post_clip3.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "#One")

    def test_slug_is_sanitised_in_the_txt_name(self):
        # The .txt inherits the PNG sanitising (no ../ outside the folder).
        written = post_instagram.write_captions(
            self.d, [("../escape", "x")], "")
        self.assertEqual(os.path.dirname(written[0]), self.d)
        self.assertNotIn("..", os.path.basename(written[0]))

    def test_non_text_caption_is_rejected(self):
        # Validates the type, as generate() already does with the cards.
        with self.assertRaises(ValueError) as e:
            post_instagram.write_captions(self.d, [("clip1", 123)], "")
        self.assertIn("clip1", str(e.exception))


class TestCaptionValidatedBeforeWriting(unittest.TestCase):
    """An invalid caption aborts BEFORE any PNG is written.

    `generate()` promises it in its docstring: validate everything before
    writing, so no half-finished material is left in a publishing folder. A
    caption of the wrong type must keep the promise the cards already keep.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        ep = layout.ensure_dir(layout.episode(self.d))
        with open(ep, "w", encoding="utf-8") as f:
            json.dump({"season": 2, "episode": 1, "city": "Stoneridge",
                       "uf": "SP", "company": "Acme", "guests":
                       [{"name": "John Doe", "role": "CEO"}]}, f)

    def _posts(self, data):
        p = layout.ensure_dir(layout.posts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"posts": data}, f)

    def test_invalid_caption_leaves_no_orphan_png(self):
        self._posts([
            {"slug": "good", "cards": ["A short quote."], "caption": "ok"},
            {"slug": "bad", "cards": ["Another quote."], "caption": 123},
        ])
        with self.assertRaises(ValueError) as e:
            post_instagram.generate(self.d)
        self.assertIn("bad", str(e.exception))
        output = layout.posts_png(self.d)
        generated = os.listdir(output) if os.path.exists(output) else []
        self.assertEqual(generated, [], f"wrote before validating: {generated}")

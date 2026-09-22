"""Tests for the shared helpers."""
import unittest

from talaria import utils


class TestStripMarkup(unittest.TestCase):
    def test_strips_english_sound_tags(self):
        self.assertEqual(utils.strip_markup("[music] we shipped it [laughter]"),
                         "we shipped it")

    def test_tag_match_is_case_insensitive(self):
        # regression: the original list was case-sensitive, so [MUSIC] went
        # burned into the video caption
        self.assertEqual(utils.strip_markup("[MUSIC] hello"), "hello")

    def test_strips_capitalised_tag(self):
        self.assertEqual(utils.strip_markup("[Applause] hello"), "hello")

    def test_strips_every_tag_in_the_set(self):
        for tag in ("[music]", "[laughter]", "[applause]", "[noise]",
                    "[silence]", "[inaudible]", "[crosstalk]"):
            self.assertEqual(utils.strip_markup(f"{tag} hello"), "hello", msg=tag)

    def test_removes_html_entities(self):
        self.assertEqual(utils.strip_markup("a &amp; b"), "a & b")

    def test_leaves_plain_text_alone(self):
        self.assertEqual(utils.strip_markup("plain text"), "plain text")

    def test_keeps_bracketed_content_that_is_not_a_sound_tag(self):
        txt = "[important] this stays"
        self.assertEqual(utils.strip_markup(txt), txt)

    def test_collapses_space_left_by_removal(self):
        self.assertEqual(utils.strip_markup("hello [music] world"), "hello world")


class TestMmss(unittest.TestCase):
    def test_format(self):
        self.assertEqual(utils.mmss(1745), "29:05")

    def test_zero(self):
        self.assertEqual(utils.mmss(0), "00:00")


class TestFixProperNouns(unittest.TestCase):
    """The caption is burned into the video: a mis-heard name ships forever.

    Automatic transcription errs on proper nouns: the same company comes back
    as Kestril, Cestril, Kestryl and Keztril in one document, and the official
    spelling is the one the episode metadata carries.
    """

    def test_variant_round_trips_to_official_spelling(self):
        for variant in ("Cestril", "Kestryl", "Keztril"):
            self.assertEqual(
                utils.fix_proper_nouns(f"we built {variant} in a garage", ["Kestril"]),
                "we built Kestril in a garage", msg=variant)

    def test_correct_spelling_is_preserved(self):
        self.assertEqual(utils.fix_proper_nouns("a Zarvik hoje", ["Zarvik"]),
                         "a Zarvik hoje")

    def test_near_miss_dictionary_word_is_left_alone(self):
        """A real word matching the pattern partway must survive it.

        "kestrel" matches the first five elements of [ck]e[sz]tr[iy]l ("kestr")
        and diverges at the sixth character, e against [iy].
        """
        txt = "the kestrel circled the field"
        self.assertEqual(utils.fix_proper_nouns(txt, ["Kestril"]), txt)

    def test_no_names_does_nothing(self):
        self.assertEqual(utils.fix_proper_nouns("texto qualquer", []), "texto qualquer")

    def test_word_boundary_is_respected(self):
        self.assertEqual(utils.fix_proper_nouns("Kestrilish", ["Kestril"]), "Kestrilish")

    def test_name_that_is_a_common_word_is_left_alone(self):
        """A client called "Delta" or "Meta" must not have the sentence rewritten.

        The correction exists for names transcription gets WRONG. When the name
        is an ordinary word, transcription already spells it right and
        capitalising it damages the sentence.
        """
        self.assertEqual(utils.fix_proper_nouns("the delta of the risk", ["Delta"]),
                         "the delta of the risk")
        self.assertEqual(utils.fix_proper_nouns("meta was the point", ["Meta"]),
                         "meta was the point")
        self.assertEqual(utils.fix_proper_nouns("a shell company", ["Shell"]),
                         "a shell company")

    def test_lowercase_occurrence_is_capitalised(self):
        """Transcription writes the name lowercase; the caption must capitalise."""
        self.assertEqual(utils.fix_proper_nouns("at kestril today", ["Kestril"]),
                         "at Kestril today")

    def test_still_corrects_an_invented_name(self):
        """The case that motivated the function still works."""
        self.assertEqual(utils.fix_proper_nouns("montar a Zarvic", ["Zarvik"]),
                         "montar a Zarvik")


class TestCleanCaption(unittest.TestCase):
    def test_deduplicates_repeated_words(self):
        self.assertEqual(utils.clean_caption("we we shipped it"), "we shipped it")

    def test_strips_hesitation_fillers(self):
        self.assertEqual(utils.clean_caption("so uh we um shipped it"),
                         "so we shipped it")

    def test_strips_sentence_initial_hesitation(self):
        self.assertEqual(utils.clean_caption("Uh, we shipped it"),
                         "we shipped it")

    def test_strips_you_know_filler(self):
        self.assertEqual(utils.clean_caption("we shipped it, you know, fast"),
                         "we shipped it, fast")

    def test_strips_filler_at_end_of_sentence(self):
        self.assertEqual(utils.clean_caption("it works, you know."),
                         "it works.")

    def test_strips_i_mean_filler(self):
        self.assertEqual(utils.clean_caption("we shipped it, I mean, fast"),
                         "we shipped it, fast")

    def test_strips_like_as_filler(self):
        self.assertEqual(utils.clean_caption("we shipped it, like, fast"),
                         "we shipped it, fast")

    def test_like_as_a_verb_survives(self):
        txt = "customers like the new flow"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_like_introducing_an_example_survives(self):
        txt = "tools, like Slack, are everywhere"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_expands_spoken_only_forms(self):
        self.assertEqual(utils.clean_caption("we gonna ship it"),
                         "we going to ship it")
        self.assertEqual(utils.clean_caption("I wanna ship it"),
                         "I want to ship it")
        self.assertEqual(utils.clean_caption("you gotta ship it"),
                         "you got to ship it")
        self.assertEqual(utils.clean_caption("it was kinda slow"),
                         "it was kind of slow")

    def test_keeps_real_contractions(self):
        txt = "we don't ship what we haven't tested"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_expansion_respects_word_boundary(self):
        txt = "a wannabe founder"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_preserves_initial_capital(self):
        self.assertEqual(utils.clean_caption("Gonna ship it"), "Going to ship it")


if __name__ == "__main__":
    unittest.main()

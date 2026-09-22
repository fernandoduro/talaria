"""Tests for hashtag generation."""
import unittest

from talaria import hashtags


class TestSlug(unittest.TestCase):
    def test_strips_accent_and_space(self):
        self.assertEqual(hashtags.slug("São Bento"), "SaoBento")

    def test_accents_in_both_words(self):
        self.assertEqual(hashtags.slug("Ribeirão Açaí"), "RibeiraoAcai")

    def test_accent_in_only_one_word(self):
        self.assertEqual(hashtags.slug("Planície Valley"), "PlanicieValley")

    def test_single_word_keeps_capitalisation(self):
        self.assertEqual(hashtags.slug("Zarvik"), "Zarvik")

    def test_strips_punctuation(self):
        self.assertEqual(hashtags.slug("A.B.C. Tech"), "ABCTech")

    def test_empty_string(self):
        self.assertEqual(hashtags.slug(""), "")


class TestBuild(unittest.TestCase):
    def test_includes_the_three_fixed_tags(self):
        tags = hashtags.build(city="Ribeirão Açaí", company="Zarvik")
        for fixed in hashtags.CHANNEL_TAGS:
            self.assertIn(fixed, tags)

    def test_includes_city_and_company(self):
        tags = hashtags.build(city="Ribeirão Açaí", company="Zarvik")
        self.assertIn("#RibeiraoAcai", tags)
        self.assertIn("#Zarvik", tags)

    def test_without_company_uses_the_fallback(self):
        tags = hashtags.build(city="Pedra Nova", company="", fallback_topic="Inovação")
        self.assertIn("#Inovacao", tags)

    def test_no_duplicates(self):
        tags = hashtags.build(city="Empreendedorismo", company="Zarvik")
        self.assertEqual(len(tags), len(set(tags)))

    def test_returns_a_formatted_string(self):
        s = hashtags.format_line(city="Pedra Nova", company="Zarvik")
        self.assertTrue(s.startswith("#"))
        self.assertIn(" ", s)


if __name__ == "__main__":
    unittest.main()

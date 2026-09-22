"""Testes da geração de hashtags."""
import unittest

from talaria import hashtags


class TestSlug(unittest.TestCase):
    def test_remove_acento_e_espaco(self):
        self.assertEqual(hashtags.slug("São Bento"), "SaoBento")

    def test_ribeirao_acai(self):
        self.assertEqual(hashtags.slug("Ribeirão Açaí"), "RibeiraoAcai")

    def test_planicie_valley(self):
        self.assertEqual(hashtags.slug("Planície Valley"), "PlanicieValley")

    def test_palavra_unica_mantem_capitalizacao(self):
        self.assertEqual(hashtags.slug("Zarvik"), "Zarvik")

    def test_remove_pontuacao(self):
        self.assertEqual(hashtags.slug("A.B.C. Tech"), "ABCTech")

    def test_string_vazia(self):
        self.assertEqual(hashtags.slug(""), "")


class TestBuild(unittest.TestCase):
    def test_inclui_as_tres_fixas(self):
        tags = hashtags.build(city="Ribeirão Açaí", company="Zarvik")
        for fixed in hashtags.CHANNEL_TAGS:
            self.assertIn(fixed, tags)

    def test_inclui_cidade_e_empresa(self):
        tags = hashtags.build(city="Ribeirão Açaí", company="Zarvik")
        self.assertIn("#RibeiraoAcai", tags)
        self.assertIn("#Zarvik", tags)

    def test_sem_empresa_usa_fallback(self):
        tags = hashtags.build(city="Pedra Nova", company="", fallback_topic="Inovação")
        self.assertIn("#Inovacao", tags)

    def test_sem_duplicatas(self):
        tags = hashtags.build(city="Empreendedorismo", company="Zarvik")
        self.assertEqual(len(tags), len(set(tags)))

    def test_retorna_string_formatada(self):
        s = hashtags.format_line(city="Pedra Nova", company="Zarvik")
        self.assertTrue(s.startswith("#"))
        self.assertIn(" ", s)


if __name__ == "__main__":
    unittest.main()

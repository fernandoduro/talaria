"""Testes da geração de hashtags."""
import unittest

from talaria import hashtags


class TestSlug(unittest.TestCase):
    def test_remove_acento_e_espaco(self):
        self.assertEqual(hashtags.slug("São Carlos"), "SaoCarlos")

    def test_sao_goncalo(self):
        self.assertEqual(hashtags.slug("São Gonçalo"), "SaoGoncalo")

    def test_sanduiche_valley(self):
        self.assertEqual(hashtags.slug("Sanduíche Valley"), "SanduicheValley")

    def test_palavra_unica_mantem_capitalizacao(self):
        self.assertEqual(hashtags.slug("Norvik"), "Norvik")

    def test_remove_pontuacao(self):
        self.assertEqual(hashtags.slug("A.B.C. Tech"), "ABCTech")

    def test_string_vazia(self):
        self.assertEqual(hashtags.slug(""), "")


class TestBuild(unittest.TestCase):
    def test_inclui_as_tres_fixas(self):
        tags = hashtags.build(cidade="São Gonçalo", empresa="Norvik")
        for fixa in hashtags.FIXAS:
            self.assertIn(fixa, tags)

    def test_inclui_cidade_e_empresa(self):
        tags = hashtags.build(cidade="São Gonçalo", empresa="Norvik")
        self.assertIn("#SaoGoncalo", tags)
        self.assertIn("#Norvik", tags)

    def test_sem_empresa_usa_fallback(self):
        tags = hashtags.build(cidade="Bauru", empresa="", fallback_tema="Inovação")
        self.assertIn("#Inovacao", tags)

    def test_sem_duplicatas(self):
        tags = hashtags.build(cidade="Empreendedorismo", empresa="Norvik")
        self.assertEqual(len(tags), len(set(tags)))

    def test_retorna_string_formatada(self):
        s = hashtags.format_line(cidade="Bauru", empresa="Norvik")
        self.assertTrue(s.startswith("#"))
        self.assertIn(" ", s)


if __name__ == "__main__":
    unittest.main()

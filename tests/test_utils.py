"""Testes dos utilitários compartilhados."""
import unittest

from talaria import utils


class TestStripMarkup(unittest.TestCase):
    def test_remove_marcacao_minuscula(self):
        self.assertEqual(utils.strip_markup("[música] olá"), "olá")

    def test_remove_marcacao_maiuscula(self):
        # regressão: a lista antiga era case-sensitive e deixava passar
        self.assertEqual(utils.strip_markup("[MÚSICA] olá"), "olá")

    def test_remove_capitalizada(self):
        self.assertEqual(utils.strip_markup("[Risadas] olá"), "olá")

    def test_remove_palmas(self):
        self.assertEqual(utils.strip_markup("[Palmas] olá"), "olá")

    def test_remove_variantes_singular_plural(self):
        for tag in ("[riso]", "[risos]", "[aplauso]", "[aplausos]"):
            self.assertEqual(utils.strip_markup(f"{tag} olá"), "olá", msg=tag)

    def test_remove_entidades_html(self):
        self.assertEqual(utils.strip_markup("a &amp; b"), "a & b")

    def test_nao_altera_texto_normal(self):
        self.assertEqual(utils.strip_markup("texto normal"), "texto normal")

    def test_nao_remove_colchete_de_conteudo(self):
        self.assertEqual(utils.strip_markup("[importante] isso fica"),
                         "[importante] isso fica")

    def test_colapsa_espaco_deixado_pela_remocao(self):
        self.assertNotIn("  ", utils.strip_markup("olá [música] mundo"))


class TestMmss(unittest.TestCase):
    def test_formato(self):
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

    def test_preserva_grafia_correta(self):
        self.assertEqual(utils.fix_proper_nouns("a Zarvik hoje", ["Zarvik"]),
                         "a Zarvik hoje")

    def test_near_miss_dictionary_word_is_left_alone(self):
        """A real word matching the pattern partway must survive it.

        "kestrel" matches the first five elements of [ck]e[sz]tr[iy]l ("kestr")
        and diverges at the sixth character, e against [iy].
        """
        txt = "the kestrel circled the field"
        self.assertEqual(utils.fix_proper_nouns(txt, ["Kestril"]), txt)

    def test_sem_nomes_nao_faz_nada(self):
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

    def test_ainda_corrige_nome_inventado(self):
        """O caso que motivou a função continua funcionando."""
        self.assertEqual(utils.fix_proper_nouns("montar a Zarvic", ["Zarvik"]),
                         "montar a Zarvik")


class TestCleanCaption(unittest.TestCase):
    def test_remove_repeticao(self):
        self.assertEqual(utils.clean_caption("eu eu gosto"), "eu gosto")

    def test_remove_muletas(self):
        self.assertNotIn(" eh ", utils.clean_caption("isso eh muito bom"))

    def test_expande_contracoes(self):
        """Contrações da fala viram forma plena na legenda queimada."""
        self.assertEqual(utils.clean_caption("tá do seu lado"), "está do seu lado")
        self.assertEqual(utils.clean_caption("pra gente poder"), "para gente poder")
        self.assertEqual(utils.clean_caption("eu tô vendo"), "eu estou vendo")
        self.assertEqual(utils.clean_caption("vou pro mercado"), "vou para mercado")

    def test_nao_expande_pro_em_locucao(self):
        """'pro labore', 'pro rata': 'pro' aqui é latim, não contração."""
        self.assertEqual(utils.clean_caption("o pro labore dos sócios"),
                         "o pro labore dos sócios")
        self.assertEqual(utils.clean_caption("dividido pro rata"),
                         "dividido pro rata")

    def test_contracao_nao_inventa_artigo(self):
        """'pra'/'pro' viram só 'para': inserir artigo erra fora do caso comum.

        "vim pra junto do Rafael" viraria "para a junto do Rafael".
        """
        self.assertEqual(utils.clean_caption("vim pra junto do Rafael"),
                         "vim para junto do Rafael")

    def test_contracao_respeita_fronteira_de_palavra(self):
        """'tá' dentro de outra palavra não pode ser trocado."""
        self.assertEqual(utils.clean_caption("está montado"), "está montado")
        self.assertEqual(utils.clean_caption("a etapa"), "a etapa")
        self.assertEqual(utils.clean_caption("compra online"), "compra online")

    def test_remove_ne_interrogativo(self):
        """'né?' é muleta de fala e polui a legenda."""
        self.assertEqual(utils.clean_caption("é isso, né?"), "é isso.")
        self.assertEqual(utils.clean_caption("olha, né, eu acho"), "olha, eu acho")

    def test_preserva_maiuscula_inicial(self):
        self.assertEqual(utils.clean_caption("Tá bom"), "Está bom")


if __name__ == "__main__":
    unittest.main()

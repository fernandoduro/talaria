"""Testes dos utilitários compartilhados."""
import unittest

from nvshorts import utils


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


class TestCorrigeNomes(unittest.TestCase):
    """A legenda tem que grafar nome próprio como o episodio.json manda.

    A transcrição automática erra nome próprio: a mesma empresa aparece como
    Norvik, Norvic, Norvyk e Norvyc no mesmo documento. Sem correção, a
    legenda queimada leva o erro para o vídeo publicado.
    """

    def test_corrige_variantes_foneticas(self):
        for errado in ("Norvic", "Norvyk", "Norvyc"):
            self.assertEqual(
                utils.corrige_nomes(f"a gente montou a {errado}, né", ["Norvik"]),
                "a gente montou a Norvik, né")

    def test_preserva_grafia_correta(self):
        self.assertEqual(utils.corrige_nomes("a Norvik hoje", ["Norvik"]),
                         "a Norvik hoje")

    def test_nao_altera_palavra_comum_parecida(self):
        """Correção não pode atropelar palavra do idioma."""
        txt = "nossa origem foi essa"
        self.assertEqual(utils.corrige_nomes(txt, ["Norvik"]), txt)

    def test_sem_nomes_nao_faz_nada(self):
        self.assertEqual(utils.corrige_nomes("texto qualquer", []), "texto qualquer")

    def test_respeita_fronteira_de_palavra(self):
        self.assertEqual(utils.corrige_nomes("Norvikzinho", ["Norvik"]), "Norvikzinho")

    def test_nao_altera_nome_que_e_palavra_do_idioma(self):
        """Cliente chamado 'Matriz' ou 'Acho' não pode reescrever a frase.

        A correção existe para nome que a transcrição ERRA. Quando o nome é
        palavra comum, a transcrição acerta e mexer só estraga.
        """
        self.assertEqual(utils.corrige_nomes("a matriz de risco", ["Matriz"]),
                         "a matriz de risco")
        self.assertEqual(utils.corrige_nomes("eu acho que sim", ["Acho"]),
                         "eu acho que sim")
        self.assertEqual(utils.corrige_nomes("na praia hoje", ["Praia"]),
                         "na praia hoje")

    def test_capitaliza_nome_em_caixa_baixa(self):
        """Transcrição escreve marca em minúscula; a legenda deve capitalizar."""
        self.assertEqual(utils.corrige_nomes("o neoboard e o quadro", ["Neoboard"]),
                         "o Neoboard e o quadro")
        self.assertEqual(utils.corrige_nomes("a norvik hoje", ["Norvik"]),
                         "a Norvik hoje")

    def test_ainda_corrige_nome_inventado(self):
        """O caso que motivou a função continua funcionando."""
        self.assertEqual(utils.corrige_nomes("montar a Norvic", ["Norvik"]),
                         "montar a Norvik")


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

        "vim pra junto do Gustavo" viraria "para a junto do Gustavo".
        """
        self.assertEqual(utils.clean_caption("vim pra junto do Gustavo"),
                         "vim para junto do Gustavo")

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

"""Testes do caption de publicação (.txt ao lado de cada peça)."""
import contextlib
import io
import os
import tempfile
import unittest

from talaria import caption


class TestMonta(unittest.TestCase):
    def test_junta_descricao_e_hashtags(self):
        t = caption.compose("A frase do corte.", "#Um #Dois")
        self.assertEqual(t, "A frase do corte.\n\n#Um #Dois")

    def test_so_descricao_quando_nao_ha_hashtags(self):
        # Sem texts.json o episódio não tem hashtags; o caption ainda serve.
        self.assertEqual(caption.compose("A frase.", ""), "A frase.")

    def test_so_hashtags_quando_nao_ha_descricao(self):
        # Corte sem post_caption: o arquivo sai, mas sem linha em branco no topo.
        self.assertEqual(caption.compose("", "#Um"), "#Um")

    def test_vazio_dos_dois_lados(self):
        self.assertEqual(caption.compose("", ""), "")

    def test_none_tratado_como_vazio(self):
        # post_caption ausente no JSON chega como None, não como "".
        self.assertEqual(caption.compose(None, None), "")
        self.assertEqual(caption.compose(None, "#Um"), "#Um")

    def test_apara_espaco_das_pontas(self):
        self.assertEqual(caption.compose("  A frase.  ", " #Um "), "A frase.\n\n#Um")


class TestEscreve(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_troca_extensao_da_peca(self):
        peca = os.path.join(self.d, "corte1_short.mp4")
        out = caption.write(peca, "texto")
        self.assertEqual(out, os.path.join(self.d, "corte1_short.txt"))
        self.assertTrue(os.path.exists(out))

    def test_conteudo_gravado_em_utf8(self):
        peca = os.path.join(self.d, "post_x.png")
        caption.write(peca, "Ação e coração.\n\n#RibeiraoAcai")
        with open(os.path.join(self.d, "post_x.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Ação e coração.\n\n#RibeiraoAcai")

    def test_sobrescreve_sem_duplicar(self):
        # Regerar duas vezes deixa um arquivo só, com o conteúdo novo.
        peca = os.path.join(self.d, "corte1_short.mp4")
        caption.write(peca, "primeira")
        caption.write(peca, "segunda")
        with open(os.path.join(self.d, "corte1_short.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "segunda")
        txts = [n for n in os.listdir(self.d) if n.endswith(".txt")]
        self.assertEqual(txts, ["corte1_short.txt"])

    def test_cria_diretorio_que_falta(self):
        peca = os.path.join(self.d, "sub", "nova", "corte1_short.mp4")
        out = caption.write(peca, "texto")
        self.assertTrue(os.path.exists(out))

    def test_nome_base_do_carrossel_vem_de_quem_chama(self):
        # O .txt do carrossel usa o slug do post, não o name do card.
        # Quem chama passa o path-base; write() só troca a extensão.
        base = os.path.join(self.d, "post_corte2.png")
        out = caption.write(base, "legenda do carrossel")
        self.assertTrue(out.endswith("post_corte2.txt"))



class TestValidaTexto(unittest.TestCase):
    """Tipo errado no JSON dá error nomeado, não AttributeError cru.

    O `compose()` é a autoridade única do formato, então a validação mora aqui:
    render e post_instagram herdam a mesma mensagem em vez de cada um escrever
    a sua (que foi como as duas versões divergiram na primeira implementação).
    """

    def test_numero_e_rejeitado_citando_o_campo_e_a_peca(self):
        with self.assertRaises(ValueError) as e:
            caption.validate("legenda", 123, "corte1")
        msg = str(e.exception)
        self.assertIn("corte1", msg)
        self.assertIn("legenda", msg)
        self.assertIn("int", msg)

    def test_lista_e_rejeitada(self):
        with self.assertRaises(ValueError) as e:
            caption.validate("post_caption", ["a"], "corte2")
        self.assertIn("list", str(e.exception))

    def test_texto_e_none_passam(self):
        # None é chave ausente no JSON — caso normal, não error.
        self.assertIsNone(caption.validate("legenda", "ok", "c1"))
        self.assertIsNone(caption.validate("legenda", None, "c1"))

class TestTravessao(unittest.TestCase):
    """O canal não usa travessão em legenda: sai com cara de texto de IA."""

    def _valida(self, valor):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            caption.validate("post_caption", valor, "corte1")
        return buf.getvalue()

    def test_avisa_quando_tem_travessao(self):
        saida = self._valida("Ele avisou — e errou assim mesmo.")
        self.assertIn("travessão", saida)
        self.assertIn("corte1", saida)

    def test_nao_avisa_sem_travessao(self):
        self.assertEqual(self._valida("Ele avisou. E errou assim mesmo."), "")

    def test_hifen_e_meia_risca_nao_disparam(self):
        # Hífen de palavra composta e meia-risca de intervalo são pontuação
        # legítima; só o travessão (—) é a construção que o gestor rejeita.
        self.assertEqual(self._valida("e-mail, 30–40 minutos"), "")

    def test_travessao_nao_aborta(self):
        # É questão de estilo: avisa e deixa seguir. Abortar travaria um
        # render inteiro por causa de um caractere.
        caption.validate("post_caption", "Com — travessão", "corte1")


class TestMontaEpisodio(unittest.TestCase):
    """Caption do episódio inteiro: título na 1ª linha, depois descrição."""

    def test_titulo_descricao_e_hashtags(self):
        t = caption.compose_episode("O Título", "A descrição.", "#Um")
        self.assertEqual(t, "O Título\n\nA descrição.\n\n#Um")

    def test_sem_titulo_nao_deixa_linha_solta(self):
        self.assertEqual(caption.compose_episode("", "A descrição.", "#Um"),
                         "A descrição.\n\n#Um")

    def test_so_titulo(self):
        self.assertEqual(caption.compose_episode("O Título", "", ""), "O Título")

    def test_none_em_qualquer_campo(self):
        self.assertEqual(caption.compose_episode(None, None, None), "")

    def test_descricao_preserva_as_proprias_quebras(self):
        # A descrição do YouTube tem blocos e separadores; não pode ser achatada.
        desc = "Linha 1\n\n---\n\nLinha 2"
        t = caption.compose_episode("T", desc, "#Um")
        self.assertIn("---", t)
        self.assertTrue(t.startswith("T\n\nLinha 1"))


if __name__ == "__main__":
    unittest.main()

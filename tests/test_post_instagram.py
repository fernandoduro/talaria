"""Testes do post de citação para Instagram."""
import json
import os
import tempfile
import unittest

from talaria import config, layout, post_instagram


class TestConfigPost(unittest.TestCase):
    def test_template_existe_no_repo(self):
        self.assertTrue(os.path.exists(config.POST_TEMPLATE),
                        f"template não encontrado em {config.POST_TEMPLATE}")

    def test_medidas_batem_com_o_template(self):
        from PIL import Image
        with Image.open(config.POST_TEMPLATE) as im:
            self.assertEqual(im.size, (config.POST_W, config.POST_H))

    def test_citacao_nao_invade_o_filete(self):
        # 5 linhas cabem; a 6ª invadiria o filete em y=2242.
        fim_5 = config.POST_CIT_Y + 4 * config.POST_CIT_PASSO + config.POST_CIT_ALTURA
        fim_6 = config.POST_CIT_Y + 5 * config.POST_CIT_PASSO + config.POST_CIT_ALTURA
        self.assertLess(fim_5, config.POST_FILETE_Y)
        self.assertGreater(fim_6, config.POST_FILETE_Y)


class TestEncaixe(unittest.TestCase):
    def test_citacao_do_design_cabe_em_5_linhas(self):
        txt = ("A gente descobriu que não precisava mudar de cidade "
               "para construir algo grande. Precisava ficar.")
        r = post_instagram.valida_card(txt)
        self.assertTrue(r["cabe"])
        self.assertEqual(r["linhas"], 5)

    def test_citacao_curta_cabe(self):
        r = post_instagram.valida_card("O mar azul estava do lado.")
        self.assertTrue(r["cabe"])
        self.assertLessEqual(r["linhas"], 5)

    def test_citacao_longa_e_rejeitada_com_o_excesso(self):
        txt = ("Às vezes a oportunidade está do seu lado e você está tão "
               "focado em uma coisa que não olha para o lado.")
        r = post_instagram.valida_card(txt)
        self.assertFalse(r["cabe"])
        self.assertGreater(r["linhas"], 5)
        self.assertIn("linha", r["motivo"])

    def test_texto_vazio_e_rejeitado(self):
        r = post_instagram.valida_card("   ")
        self.assertFalse(r["cabe"])

    def test_palavra_mais_larga_que_o_card_e_rejeitada(self):
        """Palavra sem onde quebrar sai cortada na lateral — recusa, não gera.

        A contagem de linhas não pega este caso: a palavra ocupa UMA linha e
        passa no limite de 5, mas transborda a largura. 'anticonstitucionalis-
        simamente' já estoura, e URL ou nome composto chegam lá com facilidade.
        """
        r = post_instagram.valida_card("anticonstitucionalissimamente")
        self.assertFalse(r["cabe"])
        self.assertIn("não cabe na largura", r["motivo"])

    def test_frase_com_palavra_normal_longa_ainda_cabe(self):
        """A recusa é por medida, não por tamanho de palavra em caracteres."""
        r = post_instagram.valida_card("Desenvolvimento e estruturação.")
        self.assertTrue(r["cabe"])


class TestRender(unittest.TestCase):
    def test_gera_png_no_tamanho_do_template(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            post_instagram.compoe_card(
                "O mar azul estava do lado.",
                {"nome": "Marina Siqueira", "cargo": "Sócio", "empresa": "Zarvik"},
                out,
            )
            self.assertTrue(os.path.exists(out))
            with Image.open(out) as im:
                self.assertEqual(im.size, (config.POST_W, config.POST_H))

    def test_card_que_nao_cabe_levanta_erro(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(ValueError) as ctx:
                post_instagram.compoe_card(
                    "Às vezes a oportunidade está do seu lado e você está tão "
                    "focado em uma coisa que não olha para o lado.",
                    {"nome": "X", "cargo": "Y", "empresa": "Z"},
                    out,
                )
            self.assertIn("linhas", str(ctx.exception))
            self.assertFalse(os.path.exists(out))

    def test_template_ausente_da_erro_claro(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(FileNotFoundError) as ctx:
                post_instagram.compoe_card(
                    "Curta.", {"nome": "X", "cargo": "Y", "empresa": "Z"},
                    out, template=os.path.join(d, "nao-existe.png"),
                )
            self.assertIn("template", str(ctx.exception).lower())


def _projeto_falso(d):
    """Cria um projeto mínimo com episodio.json preenchido."""
    ep = {
        "temporada": 2, "episodio": 8, "empresa": "Zarvik",
        "cidade": "Ribeirão Açaí", "uf": "SP",
        "convidados": [{"nome": "Marina Siqueira", "cargo": "Sócio",
                        "linkedin": "https://exemplo"}],
        "temas": [],
    }
    with open(layout.garante(layout.episodio(d)), "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False)
    return d


class TestAutorETexto(unittest.TestCase):
    def test_autor_vem_do_episodio_json(self):
        with tempfile.TemporaryDirectory() as d:
            _projeto_falso(d)
            a = post_instagram.autor_do_episodio(d)
            self.assertEqual(a["nome"], "Marina Siqueira")
            self.assertEqual(a["cargo"], "Sócio")
            self.assertEqual(a["empresa"], "Zarvik")

    def test_episodio_sem_convidado_usa_a_empresa(self):
        with tempfile.TemporaryDirectory() as d:
            _projeto_falso(d)
            with open(os.path.join(d, "episodio.json"), encoding="utf-8") as f:
                ep = json.load(f)
            ep["convidados"] = []
            with open(os.path.join(d, "episodio.json"), "w", encoding="utf-8") as f:
                json.dump(ep, f, ensure_ascii=False)
            a = post_instagram.autor_do_episodio(d)
            self.assertEqual(a["nome"], "Zarvik")
            self.assertEqual(a["cargo"], "")

    def test_episodio_com_dois_convidados_permite_escolher_quem_assina(self):
        """Citação do 2º convidado não pode sair com o nome do 1º.

        Atribuir a frase à pessoa errada é o pior erro desta etapa — o post
        publica nome e cargo embaixo de aspas.
        """
        with tempfile.TemporaryDirectory() as d:
            _projeto_falso(d)
            with open(os.path.join(d, "episodio.json"), encoding="utf-8") as f:
                ep = json.load(f)
            ep["convidados"].append({"nome": "Rafael Nunes", "cargo": "CEO"})
            with open(os.path.join(d, "episodio.json"), "w", encoding="utf-8") as f:
                json.dump(ep, f, ensure_ascii=False)

            padrao = post_instagram.autor_do_episodio(d)
            self.assertEqual(padrao["nome"], "Marina Siqueira")

            segundo = post_instagram.autor_do_episodio(d, quem="Rafael Nunes")
            self.assertEqual(segundo["nome"], "Rafael Nunes")
            self.assertEqual(segundo["cargo"], "CEO")

    def test_autor_desconhecido_da_erro_em_vez_de_atribuir_errado(self):
        with tempfile.TemporaryDirectory() as d:
            _projeto_falso(d)
            with self.assertRaises(ValueError) as ctx:
                post_instagram.autor_do_episodio(d, quem="Quem Nao Existe")
            self.assertIn("Quem Nao Existe", str(ctx.exception))
            self.assertIn("Marina Siqueira", str(ctx.exception))

    def test_contracoes_sao_expandidas(self):
        t = post_instagram.limpa_citacao("A oportunidade tá do seu lado", [])
        self.assertIn("está", t)
        self.assertNotIn(" tá ", f" {t} ")

    def test_nome_da_empresa_e_corrigido(self):
        t = post_instagram.limpa_citacao("A Zarvic cresceu rápido", ["Zarvik"])
        self.assertIn("Zarvik", t)
        self.assertNotIn("Zarvic", t)


class TestGerar(unittest.TestCase):
    def _com_posts(self, d, posts):
        _projeto_falso(d)
        with open(layout.garante(layout.posts(d)), "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f, ensure_ascii=False)

    def test_card_unico_gera_um_arquivo(self):
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "corte1_mar_azul",
                                 "cards": ["O mar azul estava do lado."]}])
            gerados = post_instagram.gerar(d)
            self.assertEqual(len(gerados), 1)
            self.assertTrue(gerados[0].endswith("post_corte1_mar_azul.png"))
            self.assertTrue(os.path.exists(gerados[0]))

    def test_carrossel_gera_arquivos_numerados_na_ordem(self):
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "corte3_b2b", "cards": [
                "No B2B você entrega e acabou.",
                "A responsabilidade depois é da outra pessoa.",
            ]}])
            gerados = post_instagram.gerar(d)
            self.assertEqual(len(gerados), 2)
            self.assertTrue(gerados[0].endswith("post_corte3_b2b_1.png"))
            self.assertTrue(gerados[1].endswith("post_corte3_b2b_2.png"))

    def test_card_que_estoura_aborta_sem_gerar_nada(self):
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "ok", "cards": ["Curta."]},
                                {"slug": "ruim", "cards": [
                                    "Às vezes a oportunidade está do seu lado "
                                    "e você está tão focado em uma coisa que "
                                    "não olha para o lado."]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.gerar(d)
            self.assertIn("ruim", str(ctx.exception))
            # Falha antes de escrever: nada de pasta com material pela metade.
            self.assertFalse(os.path.exists(layout.posts_png(d)))

    def test_card_que_nao_e_texto_da_erro_util(self):
        """posts.json é escrito à mão: um card numérico não pode virar
        AttributeError vindo de dentro da limpeza de texto."""
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "a", "cards": [123]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.gerar(d)
            self.assertIn("esperava texto", str(ctx.exception))

    def test_slug_com_barra_nao_escapa_da_pasta_de_saida(self):
        """Slug é digitado à mão no posts.json — não pode virar caminho.

        Sem saneamento, `../fora` cria diretório lixo e `../../..` quebra com
        FileNotFoundError obscuro do Pillow, em vez de gerar o arquivo.
        """
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "../../fora", "cards": ["Curta."]}])
            gerados = post_instagram.gerar(d)
            saida = os.path.realpath(layout.posts_png(d))
            self.assertTrue(os.path.realpath(gerados[0]).startswith(saida + os.sep))
            self.assertNotIn("..", os.path.basename(gerados[0]))

    def test_autor_do_json_e_ignorado_em_favor_do_episodio(self):
        with tempfile.TemporaryDirectory() as d:
            self._com_posts(d, [{"slug": "c1", "cards": ["Curta."],
                                 "autor": {"nome": "Nome Errado",
                                           "cargo": "X", "empresa": "Y"}}])
            post_instagram.gerar(d)
            # Não dá para ler texto do PNG; o contrato é a função de autor.
            self.assertEqual(post_instagram.autor_do_episodio(d)["nome"],
                             "Marina Siqueira")


if __name__ == "__main__":
    unittest.main()


class TestCaptionDoPost(unittest.TestCase):
    """O .txt de publicação do post — um por post, não um por card."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_card_unico_tem_txt_com_o_slug(self):
        # Post simples -> post_<slug>.txt
        saida = self.d
        escritos = post_instagram.escreve_captions(
            saida, [("corte1", "A legenda do post.")], "#Um #Dois")
        self.assertEqual(len(escritos), 1)
        self.assertTrue(escritos[0].endswith("post_corte1.txt"))
        with open(escritos[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "A legenda do post.\n\n#Um #Dois")

    def test_carrossel_gera_um_unico_txt(self):
        # 2 cards, 1 caption. É a borda principal desta feature.
        escritos = post_instagram.escreve_captions(
            self.d, [("corte2", "Legenda do carrossel.")], "#Um")
        self.assertEqual(len(escritos), 1)
        nomes = sorted(n for n in os.listdir(self.d) if n.endswith(".txt"))
        self.assertEqual(nomes, ["post_corte2.txt"])

    def test_sem_legenda_avisa_e_grava_hashtags(self):
        # Mesmo contrato do corte — não some em silêncio.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            post_instagram.escreve_captions(self.d, [("corte3", "")], "#Um")
        self.assertIn("corte3", buf.getvalue())
        self.assertIn("sem legenda", buf.getvalue())
        with open(os.path.join(self.d, "post_corte3.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "#Um")

    def test_slug_sanitizado_no_nome_do_txt(self):
        # O .txt herda a sanitização do PNG (não cria ../ fora da pasta).
        escritos = post_instagram.escreve_captions(
            self.d, [("../fuga", "x")], "")
        self.assertEqual(os.path.dirname(escritos[0]), self.d)
        self.assertNotIn("..", os.path.basename(escritos[0]))

    def test_legenda_nao_texto_e_rejeitada(self):
        # Valida tipo, como gerar() já faz com os cards.
        with self.assertRaises(ValueError) as e:
            post_instagram.escreve_captions(self.d, [("corte1", 123)], "")
        self.assertIn("corte1", str(e.exception))


class TestLegendaValidaAntesDeEscrever(unittest.TestCase):
    """Legenda inválida aborta ANTES de escrever qualquer PNG.

    O `gerar()` promete na docstring: valida tudo antes de escrever, para não
    deixar material pela metade numa pasta de publicação. Uma legenda de tipo
    errado tem que respeitar a mesma promessa que os cards já respeitam.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        ep = layout.garante(layout.episodio(self.d))
        with open(ep, "w", encoding="utf-8") as f:
            json.dump({"temporada": 2, "episodio": 1, "cidade": "Pedra Nova",
                       "uf": "SP", "empresa": "Acme", "convidados":
                       [{"nome": "Fulano de Tal", "cargo": "CEO"}]}, f)

    def _posts(self, dados):
        p = layout.garante(layout.posts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"posts": dados}, f)

    def test_legenda_invalida_nao_deixa_png_orfao(self):
        self._posts([
            {"slug": "bom", "cards": ["Uma citação curta."], "legenda": "ok"},
            {"slug": "ruim", "cards": ["Outra citação."], "legenda": 123},
        ])
        with self.assertRaises(ValueError) as e:
            post_instagram.gerar(self.d)
        self.assertIn("ruim", str(e.exception))
        saida = layout.posts_png(self.d)
        gerados = os.listdir(saida) if os.path.exists(saida) else []
        self.assertEqual(gerados, [], f"escreveu antes de validar: {gerados}")

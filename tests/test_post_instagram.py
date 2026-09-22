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
        # 5 lines cabem; a 6ª invadiria o filete em y=2242.
        end_5 = config.POST_QUOTE_Y + 4 * config.POST_QUOTE_STEP + config.POST_QUOTE_LINE_H
        end_6 = config.POST_QUOTE_Y + 5 * config.POST_QUOTE_STEP + config.POST_QUOTE_LINE_H
        self.assertLess(end_5, config.POST_RULE_Y)
        self.assertGreater(end_6, config.POST_RULE_Y)


class TestFit(unittest.TestCase):
    def test_citacao_do_design_cabe_em_5_linhas(self):
        txt = ("A gente descobriu que não precisava mudar de cidade "
               "para construir algo grande. Precisava ficar.")
        r = post_instagram.validate_card(txt)
        self.assertTrue(r["fits"])
        self.assertEqual(r["lines"], 5)

    def test_citacao_curta_cabe(self):
        r = post_instagram.validate_card("O mar azul estava do lado.")
        self.assertTrue(r["fits"])
        self.assertLessEqual(r["lines"], 5)

    def test_citacao_longa_e_rejeitada_com_o_excesso(self):
        txt = ("Às vezes a oportunidade está do seu lado e você está tão "
               "focado em uma coisa que não olha para o lado.")
        r = post_instagram.validate_card(txt)
        self.assertFalse(r["fits"])
        self.assertGreater(r["lines"], 5)
        self.assertIn("linha", r["reason"])

    def test_texto_vazio_e_rejeitado(self):
        r = post_instagram.validate_card("   ")
        self.assertFalse(r["fits"])

    def test_palavra_mais_larga_que_o_card_e_rejeitada(self):
        """Palavra sem onde quebrar sai cortada na lateral — recusa, não gera.

        A contagem de lines não pega este caso: a palavra ocupa UMA linha e
        passa no limite de 5, mas transborda a largura. 'anticonstitucionalis-
        simamente' já estoura, e URL ou name composto chegam lá com facilidade.
        """
        r = post_instagram.validate_card("anticonstitucionalissimamente")
        self.assertFalse(r["fits"])
        self.assertIn("não cabe na largura", r["reason"])

    def test_frase_com_palavra_normal_longa_ainda_cabe(self):
        """A recusa é por medida, não por tamanho de palavra em caracteres."""
        r = post_instagram.validate_card("Desenvolvimento e estruturação.")
        self.assertTrue(r["fits"])


class TestRender(unittest.TestCase):
    def test_gera_png_no_tamanho_do_template(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            post_instagram.render_card(
                "O mar azul estava do lado.",
                {"name": "Marina Siqueira", "role": "Sócio", "company": "Zarvik"},
                out,
            )
            self.assertTrue(os.path.exists(out))
            with Image.open(out) as im:
                self.assertEqual(im.size, (config.POST_W, config.POST_H))

    def test_card_que_nao_cabe_levanta_erro(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(ValueError) as ctx:
                post_instagram.render_card(
                    "Às vezes a oportunidade está do seu lado e você está tão "
                    "focado em uma coisa que não olha para o lado.",
                    {"name": "X", "role": "Y", "company": "Z"},
                    out,
                )
            self.assertIn("linhas", str(ctx.exception))
            self.assertFalse(os.path.exists(out))

    def test_template_ausente_da_erro_claro(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "post.png")
            with self.assertRaises(FileNotFoundError) as ctx:
                post_instagram.render_card(
                    "Curta.", {"name": "X", "role": "Y", "company": "Z"},
                    out, template=os.path.join(d, "nao-existe.png"),
                )
            self.assertIn("template", str(ctx.exception).lower())


def _fake_project(d):
    """Cria um project mínimo com episode.json preenchido."""
    ep = {
        "season": 2, "episode": 8, "company": "Zarvik",
        "city": "Ribeirão Açaí", "uf": "SP",
        "guests": [{"name": "Marina Siqueira", "role": "Sócio",
                        "linkedin": "https://exemplo"}],
        "topics": [],
    }
    with open(layout.ensure_dir(layout.episode(d)), "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False)
    return d


class TestAuthorAndText(unittest.TestCase):
    def test_autor_vem_do_episodio_json(self):
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            a = post_instagram.episode_author(d)
            self.assertEqual(a["name"], "Marina Siqueira")
            self.assertEqual(a["role"], "Sócio")
            self.assertEqual(a["company"], "Zarvik")

    def test_episodio_sem_convidado_usa_a_empresa(self):
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

    def test_episodio_com_dois_convidados_permite_escolher_quem_assina(self):
        """Citação do 2º convidado não pode sair com o name do 1º.

        Atribuir a frase à pessoa errada é o pior error desta etapa — o post
        publica name e role embaixo de aspas.
        """
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            with open(os.path.join(d, "episode.json"), encoding="utf-8") as f:
                ep = json.load(f)
            ep["guests"].append({"name": "Rafael Nunes", "role": "CEO"})
            with open(os.path.join(d, "episode.json"), "w", encoding="utf-8") as f:
                json.dump(ep, f, ensure_ascii=False)

            default = post_instagram.episode_author(d)
            self.assertEqual(default["name"], "Marina Siqueira")

            second = post_instagram.episode_author(d, who="Rafael Nunes")
            self.assertEqual(second["name"], "Rafael Nunes")
            self.assertEqual(second["role"], "CEO")

    def test_autor_desconhecido_da_erro_em_vez_de_atribuir_errado(self):
        with tempfile.TemporaryDirectory() as d:
            _fake_project(d)
            with self.assertRaises(ValueError) as ctx:
                post_instagram.episode_author(d, who="Quem Nao Existe")
            self.assertIn("Quem Nao Existe", str(ctx.exception))
            self.assertIn("Marina Siqueira", str(ctx.exception))

    def test_spoken_only_forms_are_expanded(self):
        t = post_instagram.clean_quote("You gotta pick one problem", [])
        self.assertIn("got to", t)
        self.assertNotIn(" gotta ", f" {t} ")

    def test_nome_da_empresa_e_corrigido(self):
        t = post_instagram.clean_quote("A Zarvic cresceu rápido", ["Zarvik"])
        self.assertIn("Zarvik", t)
        self.assertNotIn("Zarvic", t)


class TestGenerate(unittest.TestCase):
    def _with_posts(self, d, posts):
        _fake_project(d)
        with open(layout.ensure_dir(layout.posts(d)), "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f, ensure_ascii=False)

    def test_card_unico_gera_um_arquivo(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "corte1_mar_azul",
                                 "cards": ["O mar azul estava do lado."]}])
            generated = post_instagram.generate(d)
            self.assertEqual(len(generated), 1)
            self.assertTrue(generated[0].endswith("post_corte1_mar_azul.png"))
            self.assertTrue(os.path.exists(generated[0]))

    def test_carrossel_gera_arquivos_numerados_na_ordem(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "corte3_b2b", "cards": [
                "No B2B você entrega e acabou.",
                "A responsabilidade depois é da outra pessoa.",
            ]}])
            generated = post_instagram.generate(d)
            self.assertEqual(len(generated), 2)
            self.assertTrue(generated[0].endswith("post_corte3_b2b_1.png"))
            self.assertTrue(generated[1].endswith("post_corte3_b2b_2.png"))

    def test_card_que_estoura_aborta_sem_gerar_nada(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "ok", "cards": ["Curta."]},
                                {"slug": "bad", "cards": [
                                    "Às vezes a oportunidade está do seu lado "
                                    "e você está tão focado em uma coisa que "
                                    "não olha para o lado."]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.generate(d)
            self.assertIn("bad", str(ctx.exception))
            # Falha antes de escrever: nada de pasta com material pela metade.
            self.assertFalse(os.path.exists(layout.posts_png(d)))

    def test_card_que_nao_e_texto_da_erro_util(self):
        """posts.json é escrito à mão: um card numérico não pode virar
        AttributeError vindo de dentro da limpeza de texto."""
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "a", "cards": [123]}])
            with self.assertRaises(ValueError) as ctx:
                post_instagram.generate(d)
            self.assertIn("esperava texto", str(ctx.exception))

    def test_slug_com_barra_nao_escapa_da_pasta_de_saida(self):
        """Slug é digitado à mão no posts.json — não pode virar path.

        Sem saneamento, `../fora` cria diretório lixo e `../../..` quebra com
        FileNotFoundError obscuro do Pillow, em vez de generate o arquivo.
        """
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "../../fora", "cards": ["Curta."]}])
            generated = post_instagram.generate(d)
            output = os.path.realpath(layout.posts_png(d))
            self.assertTrue(os.path.realpath(generated[0]).startswith(output + os.sep))
            self.assertNotIn("..", os.path.basename(generated[0]))

    def test_autor_do_json_e_ignorado_em_favor_do_episodio(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_posts(d, [{"slug": "c1", "cards": ["Curta."],
                                 "autor": {"name": "Nome Errado",
                                           "role": "X", "company": "Y"}}])
            post_instagram.generate(d)
            # Não dá para ler texto do PNG; o contrato é a função de autor.
            self.assertEqual(post_instagram.episode_author(d)["name"],
                             "Marina Siqueira")


if __name__ == "__main__":
    unittest.main()


class TestPostCaption(unittest.TestCase):
    """O .txt de publicação do post — um por post, não um por card."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_card_unico_tem_txt_com_o_slug(self):
        # Post simples -> post_<slug>.txt
        output = self.d
        written = post_instagram.write_captions(
            output, [("corte1", "A legenda do post.")], "#Um #Dois")
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].endswith("post_corte1.txt"))
        with open(written[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "A legenda do post.\n\n#Um #Dois")

    def test_carrossel_gera_um_unico_txt(self):
        # 2 cards, 1 caption. É a borda principal desta feature.
        written = post_instagram.write_captions(
            self.d, [("corte2", "Legenda do carrossel.")], "#Um")
        self.assertEqual(len(written), 1)
        names = sorted(n for n in os.listdir(self.d) if n.endswith(".txt"))
        self.assertEqual(names, ["post_corte2.txt"])

    def test_sem_legenda_avisa_e_grava_hashtags(self):
        # Mesmo contrato do clip — não some em silêncio.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            post_instagram.write_captions(self.d, [("corte3", "")], "#Um")
        self.assertIn("corte3", buf.getvalue())
        self.assertIn("sem legenda", buf.getvalue())
        with open(os.path.join(self.d, "post_corte3.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "#Um")

    def test_slug_sanitizado_no_nome_do_txt(self):
        # O .txt herda a sanitização do PNG (não cria ../ fora da pasta).
        written = post_instagram.write_captions(
            self.d, [("../fuga", "x")], "")
        self.assertEqual(os.path.dirname(written[0]), self.d)
        self.assertNotIn("..", os.path.basename(written[0]))

    def test_legenda_nao_texto_e_rejeitada(self):
        # Valida kind, como generate() já faz com os cards.
        with self.assertRaises(ValueError) as e:
            post_instagram.write_captions(self.d, [("corte1", 123)], "")
        self.assertIn("corte1", str(e.exception))


class TestCaptionValidatedBeforeWriting(unittest.TestCase):
    """Legenda inválida aborta ANTES de escrever qualquer PNG.

    O `generate()` promete na docstring: validate tudo antes de escrever, para não
    deixar material pela metade numa pasta de publicação. Uma legenda de kind
    errado tem que respeitar a mesma promessa que os cards já respeitam.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        ep = layout.ensure_dir(layout.episode(self.d))
        with open(ep, "w", encoding="utf-8") as f:
            json.dump({"season": 2, "episode": 1, "city": "Pedra Nova",
                       "uf": "SP", "company": "Acme", "guests":
                       [{"name": "Fulano de Tal", "role": "CEO"}]}, f)

    def _posts(self, data):
        p = layout.ensure_dir(layout.posts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"posts": data}, f)

    def test_legenda_invalida_nao_deixa_png_orfao(self):
        self._posts([
            {"slug": "bom", "cards": ["Uma citação curta."], "caption": "ok"},
            {"slug": "bad", "cards": ["Outra citação."], "caption": 123},
        ])
        with self.assertRaises(ValueError) as e:
            post_instagram.generate(self.d)
        self.assertIn("bad", str(e.exception))
        output = layout.posts_png(self.d)
        generated = os.listdir(output) if os.path.exists(output) else []
        self.assertEqual(generated, [], f"escreveu antes de validar: {generated}")

"""Testes do layout de arquivos do projeto."""
import os
import tempfile
import unittest

from nvshorts import layout


class TestCaminhos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_episodio_fica_na_raiz(self):
        self.assertEqual(layout.episodio(self.d),
                         os.path.join(self.d, "episodio.json"))

    def test_fonte_agrupada(self):
        self.assertTrue(layout.video(self.d).endswith("fonte/video.mp4"))
        self.assertTrue(layout.transcricao(self.d).endswith("fonte/transcricao.json"))
        self.assertTrue(layout.transcricao_txt(self.d).endswith("fonte/transcricao.txt"))

    def test_decisoes_agrupadas(self):
        for f in (layout.curadoria(self.d), layout.momentos(self.d),
                  layout.textos(self.d), layout.posts(self.d)):
            self.assertIn("/decisoes/", f)

    def test_briefs_por_tipo(self):
        self.assertTrue(layout.brief(self.d, "cortes").endswith("briefs/cortes.md"))
        self.assertTrue(layout.brief(self.d, "posts").endswith("briefs/posts.md"))

    def test_publicaveis_agrupados(self):
        self.assertTrue(layout.thumbnail(self.d).endswith("publicar/thumbnail.jpg"))
        self.assertTrue(layout.plataforma(self.d, "youtube_shorts")
                        .endswith("publicar/youtube_shorts"))
        self.assertTrue(layout.posts_png(self.d).endswith("publicar/instagram_posts"))

    def test_garante_cria_a_pasta_do_arquivo(self):
        alvo = layout.garante(layout.momentos(self.d))
        self.assertTrue(os.path.isdir(os.path.dirname(alvo)))


class TestMigracao(unittest.TestCase):
    ANTIGOS = ["fonte.mp4", "transcricao.json", "transcricao.txt",
               "curadoria.json", "momentos.json", "textos.json", "posts.json",
               "brief_materiais.md", "brief_cortes.md", "brief_posts.md",
               "thumbnail.jpg", "_thumb_frame.jpg", "episodio.json"]

    def _projeto_antigo(self):
        d = tempfile.mkdtemp()
        for nome in self.ANTIGOS:
            with open(os.path.join(d, nome), "w", encoding="utf-8") as f:
                f.write(nome)
        for sub in ("youtube_shorts", "instagram_reels", "instagram_posts"):
            os.makedirs(os.path.join(d, sub))
            with open(os.path.join(d, sub, "x.mp4"), "w") as f:
                f.write("x")
        return d

    def test_move_tudo_para_o_lugar_certo(self):
        d = self._projeto_antigo()
        movidos = layout.migrar(d)
        self.assertGreater(len(movidos), 0)
        self.assertTrue(os.path.exists(layout.video(d)))
        self.assertTrue(os.path.exists(layout.transcricao(d)))
        self.assertTrue(os.path.exists(layout.momentos(d)))
        self.assertTrue(os.path.exists(layout.brief(d, "cortes")))
        self.assertTrue(os.path.exists(layout.thumbnail(d)))
        self.assertTrue(os.path.exists(
            os.path.join(layout.plataforma(d, "youtube_shorts"), "x.mp4")))

    def test_conteudo_preservado(self):
        d = self._projeto_antigo()
        layout.migrar(d)
        with open(layout.momentos(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "momentos.json")

    def test_episodio_json_fica_na_raiz(self):
        d = self._projeto_antigo()
        layout.migrar(d)
        self.assertTrue(os.path.exists(layout.episodio(d)))
        self.assertEqual(os.path.dirname(layout.episodio(d)), d)

    def test_lixo_temporario_e_removido(self):
        d = self._projeto_antigo()
        layout.migrar(d)
        self.assertFalse(os.path.exists(os.path.join(d, "_thumb_frame.jpg")))

    def test_raiz_fica_so_com_episodio_e_as_pastas(self):
        d = self._projeto_antigo()
        layout.migrar(d)
        na_raiz = {n for n in os.listdir(d) if not n.startswith(".")}
        self.assertEqual(na_raiz, {"episodio.json", "fonte", "decisoes",
                                   "briefs", "publicar"})

    def test_e_idempotente(self):
        d = self._projeto_antigo()
        layout.migrar(d)
        self.assertEqual(layout.migrar(d), [])   # 2ª vez não move nada
        self.assertTrue(os.path.exists(layout.momentos(d)))

    def test_projeto_novo_nao_e_afetado(self):
        d = tempfile.mkdtemp()
        self.assertEqual(layout.migrar(d), [])

    def test_nao_sobrescreve_arquivo_ja_migrado(self):
        """Se os dois existem, o da posição NOVA vence — é o mais recente."""
        d = self._projeto_antigo()
        layout.migrar(d)
        with open(layout.momentos(d), "w", encoding="utf-8") as f:
            f.write("NOVO")
        with open(os.path.join(d, "momentos.json"), "w", encoding="utf-8") as f:
            f.write("ANTIGO")
        layout.migrar(d)
        with open(layout.momentos(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "NOVO")
        # e o antigo é preservado como .bak, não apagado
        with open(os.path.join(d, "momentos.json.bak"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "ANTIGO")


class TestMigracaoDefensiva(unittest.TestCase):
    """Cenários em que a migração poderia perder ou esconder trabalho."""

    def test_duplicata_nao_e_apagada_em_silencio(self):
        """Arquivo nos dois lugares: o novo vence, mas o antigo vira .bak.

        Cenário real: o gestor copia um momentos.json de backup para a raiz
        para restaurar algo. Sem isto, o próximo comando o apagaria sem dizer
        nada — e o relatório de migração viria vazio.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.DECISOES))
        with open(layout.momentos(d), "w", encoding="utf-8") as f:
            f.write("NOVO")
        with open(os.path.join(d, "momentos.json"), "w", encoding="utf-8") as f:
            f.write("ANTIGO")

        movidos = layout.migrar(d)

        with open(layout.momentos(d), encoding="utf-8") as f:
            self.assertEqual(f.read(), "NOVO")          # o novo continua valendo
        self.assertFalse(os.path.exists(os.path.join(d, "momentos.json")))
        bak = os.path.join(d, "momentos.json.bak")
        self.assertTrue(os.path.exists(bak))            # o antigo não sumiu
        with open(bak, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ANTIGO")
        self.assertTrue(any("bak" in destino for _, destino in movidos),
                        f"o relatório precisa mencionar o .bak: {movidos}")

    def test_nome_de_pasta_ocupado_por_arquivo_da_erro_util(self):
        """Um arquivo chamado 'decisoes' impede a pasta — o erro tem que dizer isso."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "momentos.json"), "w", encoding="utf-8") as f:
            f.write("x")
        with open(os.path.join(d, layout.DECISOES), "w", encoding="utf-8") as f:
            f.write("sou um arquivo, não uma pasta")

        with self.assertRaises(RuntimeError) as ctx:
            layout.migrar(d)
        msg = str(ctx.exception)
        self.assertIn(layout.DECISOES, msg)
        self.assertIn("pasta", msg.lower())
        # nada foi perdido: o arquivo original continua onde estava
        self.assertTrue(os.path.exists(os.path.join(d, "momentos.json")))


    def test_avisa_quando_a_duplicata_descartada_e_maior(self):
        """Arquivo pela metade na posição nova não pode passar despercebido.

        O tamanho não decide qual vale (um JSON menor é normal), mas um vídeo
        de 15 bytes virando o ativo enquanto o de 2GB vira .bak precisa saltar
        aos olhos no relatório.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.FONTE))
        with open(layout.video(d), "w") as f:
            f.write("X" * 15)                     # stub na posição nova
        with open(os.path.join(d, "fonte.mp4"), "w") as f:
            f.write("V" * 30000)                  # vídeo real na antiga

        movidos = layout.migrar(d)

        self.assertTrue(any("MAIOR" in destino for _, destino in movidos),
                        f"o relatório precisa avisar: {movidos}")

    def test_pasta_de_saida_duplicada_e_reportada(self):
        """Pasta antiga com conteúdo que a nova não tem não pode ficar órfã.

        Sem aviso, dois cortes já renderizados ficariam fora da estrutura
        documentada — e sumiriam na próxima limpeza da pasta do episódio.
        """
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, layout.PUBLICAR, "youtube_shorts"))
        with open(os.path.join(d, layout.PUBLICAR, "youtube_shorts", "c1.mp4"), "w") as f:
            f.write("novo")
        os.makedirs(os.path.join(d, "youtube_shorts"))
        for n in ("c1.mp4", "c2.mp4"):
            with open(os.path.join(d, "youtube_shorts", n), "w") as f:
                f.write("antigo " + n)

        movidos = layout.migrar(d)

        # o que só existia na antiga foi trazido
        destino = os.path.join(d, layout.PUBLICAR, "youtube_shorts")
        self.assertTrue(os.path.exists(os.path.join(destino, "c2.mp4")))
        # o que já existia na nova não foi sobrescrito
        with open(os.path.join(destino, "c1.mp4"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "novo")
        # e o relatório não fica em silêncio
        self.assertTrue(movidos, "mover conteúdo órfão precisa aparecer no relatório")
        self.assertFalse(os.path.isdir(os.path.join(d, "youtube_shorts")))

    def test_interrupcao_e_recuperavel(self):
        """Migração parcial: rodar de novo termina o serviço, sem perder nada."""
        import shutil as _sh
        d = tempfile.mkdtemp()
        nomes = ("fonte.mp4", "momentos.json", "curadoria.json", "textos.json",
                 "brief_cortes.md", "thumbnail.jpg")
        for n in nomes:
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write(n)

        original = _sh.move
        estado = {"n": 0}

        def move_que_morre(a, b):
            estado["n"] += 1
            if estado["n"] == 3:
                raise KeyboardInterrupt("simula ctrl-c no meio")
            return original(a, b)

        _sh.move = move_que_morre
        try:
            with self.assertRaises(KeyboardInterrupt):
                layout.migrar(d)
        finally:
            _sh.move = original

        layout.migrar(d)                      # 2ª execução completa

        sobreviventes = []
        for raiz, _, arquivos in os.walk(d):
            sobreviventes += arquivos
        self.assertEqual(len(sobreviventes), len(nomes))
        self.assertTrue(os.path.exists(layout.momentos(d)))
        self.assertTrue(os.path.exists(layout.video(d)))


if __name__ == "__main__":
    unittest.main()


class TestCaptionDoEpisodio(unittest.TestCase):
    def test_fica_na_raiz_de_publicar(self):
        # Ao lado da thumbnail: são os dois artefatos do episódio inteiro,
        # não de uma peça específica.
        d = tempfile.mkdtemp()
        self.assertEqual(layout.episodio_txt(d),
                         os.path.join(d, "publicar", "episodio.txt"))


class TestCaminhosPublicacao(unittest.TestCase):
    def test_calendario_em_decisoes(self):
        self.assertEqual(layout.calendario("/p/ep8"),
                         os.path.join("/p/ep8", "decisoes", "calendario.json"))

    def test_publicado_em_decisoes(self):
        self.assertEqual(layout.publicado("/p/ep8"),
                         os.path.join("/p/ep8", "decisoes", "publicado.json"))

"""Montagem dos segmentos de legenda dentro de um clip."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from talaria import audio, config, layout, render


class TestValleyBefore(unittest.TestCase):
    """Pausa só account como end de fala se o silêncio DURAR.

    Numa fala corrida a energia mergulha entre words a cada ~100ms. Cortar
    no primeiro mergulho parte a frase: um clip terminou numa pausa
    interna de 80ms e a fala sumiu antes de "...project assim tão longo".
    """

    def _points(self, spec):
        """[(t, dB)] a partir de [(n_janelas, dB)]."""
        points, t = [], 0.0
        for n, db in spec:
            for _ in range(n):
                points.append((round(t, 3), db))
                t += audio.WINDOW_S
        return points

    def test_ignora_pausa_interna_curta(self):
        """4 janelas (80ms) de silêncio no meio da fala não é end de frase."""
        points = self._points([(10, -18.0), (4, -44.0), (10, -18.0)])
        i = 10
        self.assertLess(
            audio._silence_duration(points, i, audio.PAUSE_THRESHOLD_DB),
            audio.SILENCE_MIN_S)

    def test_aceita_silencio_longo(self):
        """15 janelas (300ms) de silêncio é end de fala."""
        points = self._points([(10, -18.0), (15, -44.0)])
        self.assertGreaterEqual(
            audio._silence_duration(points, 10, audio.PAUSE_THRESHOLD_DB),
            audio.SILENCE_MIN_S)

    def test_silencio_minimo_e_maior_que_pausa_entre_palavras(self):
        """Pausa entre words roda em 40-100ms; o threshold tem que ficar acima."""
        self.assertGreater(audio.SILENCE_MIN_S, 0.12)


class TestAdjustRespectsMinimum(unittest.TestCase):
    """Nem o vale nem a margem podem levar o clip abaixo da duração mínima."""

    def test_margem_nao_derruba_abaixo_do_minimo(self):
        from talaria import config
        start = 100.0
        end = start + config.CLIP_MIN_S          # exatamente no limite
        self.assertGreaterEqual(
            render.apply_end_margin(end, start) - start, config.CLIP_MIN_S)


class TestClipsMidWord(unittest.TestCase):
    """Distinguir fala que TERMINA de fala que foi CORTADA.

    Toda fala acaba com uma sílaba, então "tem energia no end" acusa qualquer
    clip. O sinal é o decaimento: palavra terminando decai; palavra cortada
    para de repente ainda no nível alto. Números medidos.
    """

    def test_limiar_separa_os_casos_medidos(self):
        # clip defeituoso: -31 -28 -31 (estável, alto)
        self.assertFalse(self._decays([-31.1, -28.5, -30.6]))
        # "importadas." correto: -25.8 -> -39.4 (despenca)
        self.assertTrue(self._decays([-25.8, -25.9, -39.4]))

    def _decays(self, dbs, threshold=-25.0):
        """Reproduz a decisão de clips_mid_word sobre uma série já medida."""
        if dbs[-1] <= threshold - 10.0:
            return True
        return (dbs[0] - dbs[-1]) >= 8.0

    def test_silencio_no_fim_nunca_acusa(self):
        self.assertTrue(self._decays([-44.0, -46.0, -48.0]))

    def test_janela_e_estreita(self):
        """Janela larga pegaria a sílaba final de qualquer fala."""
        import inspect
        sig = inspect.signature(audio.clips_mid_word)
        self.assertLessEqual(sig.parameters["window"].default, 0.08)


class TestEndMargin(unittest.TestCase):
    """O end do clip precisa de folga para não pegar a palavra seguinte.

    Os tempos vêm da transcrição, cuja resolução é de 1 segundo — cortar
    exatamente no limite de um bloco encosta no ataque da próxima palavra. Um
    clip terminava em 901.0 e deixava vazar o "Poucas" que abre o bloco
    seguinte (a pausa entre as duas words dura ~50ms).
    """

    def test_recua_o_fim_pela_margem(self):
        """Corte com folga sobre o mínimo recua a margem inteira."""
        self.assertAlmostEqual(render.apply_end_margin(901.0, 830.0),
                               901.0 - render.END_MARGIN_S)

    def test_margem_nao_inverte_o_corte(self):
        """Corte curto demais para a margem mantém pelo menos o início."""
        end = render.apply_end_margin(10.05, 10.0)
        self.assertGreater(end, 10.0)

    def test_margem_e_pequena(self):
        """Margem grande cortaria a última sílaba da fala aproveitada."""
        self.assertLessEqual(render.END_MARGIN_S, 0.15)


class TestSegmentsInCut(unittest.TestCase):
    """O texto exibido não pode passar do que o áudio do clip alcança.

    Os tempos já eram aparados pelo clip (min/max), mas o TEXTO ia inteiro
    para o PNG: um segmento aparado em 1.4s continuava mostrando as 150
    letras do bloco original. O clip fechava em "vai conseguir
    reproduzir" e a tela seguia exibindo "Acho que isso é uma um primeiro
    ponto..." — frase que o espectador nunca ouve.
    """

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 10.0, "text": "Primeira fala inteira.", "turn": False},
            {"start": 10.0, "end": 20.0,
             "text": "Vai conseguir reproduzir. Acho que isso é um primeiro ponto.",
             "turn": False},
            {"start": 20.0, "end": 30.0, "text": "Depois do corte.", "turn": False},
        ]

    def test_segmento_fora_do_corte_nao_entra(self):
        items = render._segments_in_cut(self.segs, 0.0, 20.0)
        self.assertEqual(len(items), 2)
        self.assertNotIn("Depois do corte", " ".join(t for _, _, t in items))

    def test_tempos_sao_relativos_ao_inicio_do_corte(self):
        items = render._segments_in_cut(self.segs, 10.0, 30.0)
        self.assertEqual(items[0][0], 0.0)

    def test_texto_aparado_quando_corte_termina_no_meio(self):
        """Corte em 15.0 pega metade do bloco 10-20: texto tem que encolher."""
        items = render._segments_in_cut(self.segs, 0.0, 15.0)
        last = items[-1][2]
        self.assertIn("Vai conseguir reproduzir", last)
        self.assertNotIn("primeiro ponto", last)

    def test_texto_inteiro_quando_segmento_cabe_no_corte(self):
        items = render._segments_in_cut(self.segs, 0.0, 20.0)
        self.assertIn("primeiro ponto", items[-1][2])

    def test_ignora_fatia_curta_demais_para_ler(self):
        """Sobra de milissegundos no end não pode virar legenda piscando.

        O clip termina alguns ms depois do início do bloco seguinte (o end vem
        do vale de áudio, não da grade da transcrição). Sem floor de duração,
        esse bloco vira um PNG de 1 frame — o clip exibia "Poucas"
        por 20ms, justamente a palavra que o ajuste de áudio tirou.
        """
        segs = [
            {"start": 0.0, "end": 60.0, "text": "Fala aproveitada.", "turn": False},
            {"start": 60.0, "end": 70.0, "text": "Poucas pessoas fazendo.", "turn": False},
        ]
        items = render._segments_in_cut(segs, 0.0, 60.02)
        self.assertEqual(len(items), 1, items)
        self.assertNotIn("Poucas", " ".join(t for _, _, t in items))

    def test_mantem_fatia_curta_mas_legivel(self):
        """Piso não pode engolir legenda curta legítima."""
        segs = [
            {"start": 0.0, "end": 60.0, "text": "Fala aproveitada.", "turn": False},
            {"start": 60.0, "end": 70.0, "text": "Sim.", "turn": False},
        ]
        items = render._segments_in_cut(segs, 0.0, 61.0)
        self.assertEqual(len(items), 2, items)

    def test_texto_aparado_no_inicio_do_corte(self):
        """Corte começando no meio de um bloco não mostra o que já passou."""
        items = render._segments_in_cut(self.segs, 15.0, 30.0)
        first = items[0][2]
        self.assertNotIn("Vai conseguir reproduzir", first)

    def test_apara_estende_ate_pontuacao_proxima(self):
        """Fatia que para 1-2 words antes do ponto final deve alcançá-lo.

        Truncar antes da pontuação deixa a legenda pendurada ("muito mais do")
        quando o áudio completou a frase ("muito mais do mesmo."). Caso real.
        """
        txt = "muito mais do mesmo. para cápsula, comprimido."
        self.assertEqual(render._trim_text(txt, 0.0, 0.25), "muito mais do mesmo.")

    def test_apara_nao_estende_atraves_de_frase_inteira(self):
        """A extensão é local: não pode arrastar a frase seguinte inteira."""
        txt = "primeira. " + " ".join(f"p{i}" for i in range(20)) + " end."
        out = render._trim_text(txt, 0.0, 0.2)
        self.assertNotIn("end.", out)

    def test_apara_respeita_fronteira_de_palavra(self):
        """O texto aparado nunca termina com palavra pela metade."""
        items = render._segments_in_cut(self.segs, 0.0, 13.0)
        last = items[-1][2]
        self.assertFalse(last.endswith("re"), last)
        for word in last.split():
            self.assertIn(word.strip(".,!?"),
                          self.segs[1]["text"].replace(".", " ").split())


class TestWrapByPixels(unittest.TestCase):
    """wrap_by_pixels serve a legenda queimada E o post de citação."""

    DESIGN_QUOTE = ("A gente descobriu que não precisava mudar de cidade "
                         "para construir algo grande. Precisava ficar.")

    def test_wrap_aceita_fonte_e_largura_alternativas(self):
        """A quebra serve a legenda e ao post, que têm fonte e largura diferentes.

        Mede propriedades que valem em QUALQUER fonte: nenhuma linha passa da
        largura, e nenhuma palavra some ou troca de ordem. A conferência contra
        a quebra de referência fica no teste seguinte, que exige a fonte certa.
        """
        from PIL import ImageFont
        from talaria import config, render
        fnt = ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)
        lines = render.wrap_by_pixels(self.DESIGN_QUOTE, fnt=fnt,
                                       width=config.POST_TEXT_W)
        self.assertGreater(len(lines), 1)
        for line in lines:
            # Palavra sozinha maior que a largura é exceção conhecida: ela vai
            # para a linha mesmo assim, porque não há onde quebrar.
            if len(line.split()) > 1:
                self.assertLessEqual(fnt.getlength(line),
                                     config.POST_TEXT_W)
        self.assertEqual(" ".join(lines), self.DESIGN_QUOTE)

    def test_quebra_do_design_com_a_fonte_do_design(self):
        """A citação de referência quebra em 5 lines na fonte versionada.

        Não há mais cadeia de candidatas: a fonte vem de assets/fonts/, então
        a quebra é a mesma em qualquer máquina e o teste cobra o layout em vez
        de pular.
        """
        from PIL import ImageFont
        from talaria import config, render
        fnt = ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)
        self.assertEqual(fnt.getname(), ("Poppins", "SemiBold"))
        lines = render.wrap_by_pixels(self.DESIGN_QUOTE, fnt=fnt,
                                       width=config.POST_TEXT_W)
        self.assertEqual(lines, ["A gente descobriu que",
                                  "não precisava mudar",
                                  "de cidade para",
                                  "construir algo grande.",
                                  "Precisava ficar."])

    def test_wrap_sem_argumentos_mantem_o_comportamento_da_legenda(self):
        from talaria import render
        lines = render.wrap_by_pixels("palavra " * 30)
        self.assertGreater(len(lines), 1)


if __name__ == "__main__":
    unittest.main()


class TestSuggestFrames(unittest.TestCase):
    """Onde procurar frame de thumbnail: dentro dos cortes approved.

    A escolha final é visual e fica com o gestor — o que se automatiza é a
    região. A sugestão caiu em 1619s e o frame escolhido à mão foi 1620s.
    """

    def setUp(self):
        from talaria import thumbnail
        self.thumbnail = thumbnail
        self.moments = [{"start": s, "end": s + 60.0}
                         for s in (100.0, 500.0, 900.0, 1300.0, 1700.0, 2100.0)]

    def test_sugere_dentro_dos_cortes(self):
        for t in self.thumbnail.suggest_frames(self.moments):
            self.assertTrue(any(m["start"] <= t <= m["end"] for m in self.moments),
                            f"{t} fora de qualquer corte")

    def test_respeita_o_limite_pedido(self):
        self.assertLessEqual(len(self.thumbnail.suggest_frames(self.moments, n=3)), 3)

    def test_menos_cortes_que_o_limite(self):
        r = self.thumbnail.suggest_frames(self.moments[:2], n=5)
        self.assertEqual(len(r), 2)

    def test_sem_momentos(self):
        self.assertEqual(self.thumbnail.suggest_frames([]), [])


class TestClipCaption(unittest.TestCase):
    """O .txt de publicação gravado ao lado de cada peça renderizada."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _texts(self, data):
        p = layout.ensure_dir(layout.texts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _episode(self, url):
        p = layout.ensure_dir(layout.episode(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"youtube_url": url}, f)

    def test_grava_txt_para_cada_plataforma(self):
        # Cada peça renderizada ganha um .txt irmão.
        self._texts({"hashtags": "#Um #Dois"})
        pieces = [os.path.join(self.d, "youtube_shorts", "c1_short.mp4"),
                 os.path.join(self.d, "instagram_reels", "c1_reel.mp4")]
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "A frase."}, pieces)
        for p in pieces:
            txt = p[:-4] + ".txt"
            self.assertTrue(os.path.exists(txt), txt)
            with open(txt, encoding="utf-8") as f:
                self.assertEqual(f.read(), "A frase.\n\n#Um #Dois")

    def test_sem_legenda_post_avisa_e_grava_hashtags(self):
        # Ausência não pode passar silenciosa.
        self._texts({"hashtags": "#Um"})
        piece = os.path.join(self.d, "youtube_shorts", "c5_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c5"}, [piece])
        self.assertIn("c5", buf.getvalue())
        self.assertIn("sem post_caption", buf.getvalue())
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "#Um")

    def test_com_legenda_post_nao_avisa(self):
        self._texts({"hashtags": "#Um"})
        self._episode("https://youtu.be/XYZ")
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "A frase."}, [piece])
        self.assertEqual(buf.getvalue(), "")

    def test_sem_textos_json_nao_quebra(self):
        # Episódio sem texts.json ainda rende caption.
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "A frase."}, [piece])
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "A frase.")


    def test_link_do_episodio_so_no_youtube(self):
        # A URL do episódio entra na descrição do Short e NÃO na legenda do
        # Reels: no Instagram ela não é clicável e manda o leitor para fora.
        self._texts({"hashtags": "#Um"})
        self._episode("https://youtu.be/XYZ")
        yt = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        ig = os.path.join(self.d, "instagram_reels", "c1_reel.mp4")
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "A frase."}, [yt, ig])
        with open(yt[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(
                f.read(),
                "A frase.\n\n▶ Episódio completo: https://youtu.be/XYZ\n\n#Um")
        with open(ig[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "A frase.\n\n#Um")

    def test_sem_url_youtube_avisa_e_grava_sem_o_link(self):
        # Corte renderizado antes de o vídeo longo subir é o caso normal —
        # não pode quebrar, mas também não pode passar silencioso: o Short
        # iria ao ar sem a chamada, e isso só se percebe depois de published.
        self._texts({"hashtags": "#Um"})
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "A frase."},
                                    [piece])
        self.assertIn("youtube_url", buf.getvalue())
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "A frase.\n\n#Um")

    def test_episodio_json_invalido_nao_quebra_o_caption(self):
        # episode.json incompleto aborta no `load`, que validate o episódio
        # inteiro. O caption lê só a URL, que é opcional, e segue sem ela.
        self._texts({"hashtags": "#Um"})
        with open(layout.ensure_dir(layout.episode(self.d)), "w",
                  encoding="utf-8") as f:
            f.write("{ nao é json")
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        with contextlib.redirect_stdout(io.StringIO()):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "A frase."},
                                    [piece])
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "A frase.\n\n#Um")


class TestEpisodeCaption(unittest.TestCase):
    """O .txt com título e descrição do episódio, na raiz de publish/."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _texts(self, data):
        p = layout.ensure_dir(layout.texts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _episode(self, url):
        p = layout.ensure_dir(layout.episode(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"youtube_url": url}, f)

    def test_grava_titulo_descricao_e_hashtags(self):
        self._texts({"title": "O Título", "description": "A descrição.",
                      "hashtags": "#Um"})
        out = render.write_episode_caption(self.d)
        self.assertEqual(out, layout.episode_txt(self.d))
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "O Título\n\nA descrição.\n\n#Um")

    def test_sem_textos_json_nao_grava_nem_quebra(self):
        # Episódio antes da etapa de materiais: não há o que colar ainda.
        self.assertIsNone(render.write_episode_caption(self.d))
        self.assertFalse(os.path.exists(layout.episode_txt(self.d)))

    def test_textos_json_vazio_nao_gera_arquivo(self):
        self._texts({})
        self.assertIsNone(render.write_episode_caption(self.d))
        self.assertFalse(os.path.exists(layout.episode_txt(self.d)))


class TestWatermarkGraph(unittest.TestCase):
    """O overlay da marca d'água, encadeado depois de [outv]."""

    def test_encadeia_apos_outv_e_produz_outv2(self):
        fg = render._watermark_graph("outv", "logoinput")
        self.assertIn("[outv]", fg)
        self.assertIn("[logoinput]", fg)
        self.assertTrue(fg.strip().endswith("[outv2]"))

    def test_usa_margem_e_largura_do_config(self):
        fg = render._watermark_graph("outv", "3")
        self.assertIn(f"scale={config.WATERMARK_W}", fg)
        self.assertIn(f"W-w-{config.WATERMARK_MARGIN}", fg)
        self.assertIn(f"{config.WATERMARK_MARGIN}[outv2]", fg)


def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None


class TestWatermarkAndCardIntegration(unittest.TestCase):
    """Render real, com ffmpeg de verdade: confirma que o comando roda e
    produz um arquivo com marca d'água + card, não só que a string do
    filtergraph parece certa.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg não disponível")
    def test_corte_sai_com_marca_dagua_e_card(self):
        video = layout.ensure_dir(layout.video(self.d))
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:d=8:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-shortest", video,
        ], check=True)

        segs = [{"start": 0.5, "end": 4.0, "text": "Legenda de teste.", "turn": False},
                {"start": 4.0, "end": 7.5, "text": "Segunda legenda.", "turn": True}]
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f)
        moment = {"slug": "c1", "start": 0.0, "end": 8.0}
        with open(layout.ensure_dir(layout.moments(self.d)), "w", encoding="utf-8") as f:
            json.dump([moment], f)

        render.render_all(self.d, ["youtube"])

        out = os.path.join(layout.platform(self.d, "youtube_shorts"), "c1_short.mp4")
        self.assertTrue(os.path.exists(out))

        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out], capture_output=True, text=True, check=True)
        duration = float(r.stdout.strip())
        # A duração do clip propriamente dito varia com o ajuste por áudio
        # (adjust_end_by_audio); o card acrescenta CARD_DURATION_S por cima.
        self.assertGreater(duration, config.CARD_DURATION_S)

        # O card cacheado deve existir na raiz de publish/ (não numa pasta
        # de platform) e ser reaproveitado, não um por clip.
        card = layout.end_card_mp4(self.d)
        self.assertTrue(os.path.exists(card))


class TestConcatenateEndCard(unittest.TestCase):
    """Concatenação clip + card pelo concat filter."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg não disponível")
    def test_duracao_final_e_corte_mais_card(self):
        clip = os.path.join(self.d, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=1080x1920:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)

        render.append_end_card(clip, self.d)

        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", clip], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               2.0 + config.CARD_DURATION_S, delta=0.3)

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg não disponível")
    def test_e_operacao_no_lugar_mesmo_caminho(self):
        clip = os.path.join(self.d, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)

        before = os.path.getsize(clip)
        render.append_end_card(clip, self.d)
        self.assertTrue(os.path.exists(clip))
        self.assertGreater(os.path.getsize(clip), before)

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg não disponível")
    def test_caminho_com_apostrofo_nao_quebra(self):
        # Slug de project digitado à mão pode ter apóstrofo.
        subdir = os.path.join(self.d, "proj's episode")
        os.makedirs(subdir, exist_ok=True)
        clip = os.path.join(subdir, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=green:s=1080x1920:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)
        render.append_end_card(clip, subdir)
        self.assertTrue(os.path.exists(clip))


class TestClipsMidWordOrderBeforeCard(unittest.TestCase):
    """clips_mid_word precisa medir o clip ANTES do card ser concatenado.

    Risco real: se a checagem rodar no arquivo já com o card grudado, o
    instante medido (end-start) cai perto de onde o card MUDO começa. A
    janela de leitura tem folga (180ms) ao redor desse ponto — dependendo de
    arredondamento de frame ela pode capturar silêncio do card em vez da
    fala, mascarando um clip de palavra real. Em vez de depender de threshold
    de áudio (frágil, sensível a codec/timing), o teste trava o CONTRATO:
    clips_mid_word tem que ser chamado com um arquivo que NÃO tem a duração do
    card somada — ou seja, antes da concatenação.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg não disponível")
    def test_cauda_vaza_roda_antes_da_concatenacao(self):
        video = layout.ensure_dir(layout.video(self.d))
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:d=5:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-shortest", video,
        ], check=True)
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": []}, f)
        with open(layout.ensure_dir(layout.moments(self.d)), "w", encoding="utf-8") as f:
            json.dump([{"slug": "c1", "start": 0.0, "end": 5.0}], f)

        durations_seen = []
        original = audio.clips_mid_word

        def spy(video_path, end, *a, **kw):
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, check=True)
            durations_seen.append(float(r.stdout.strip()))
            return original(video_path, end, *a, **kw)

        import unittest.mock as mock
        with mock.patch("talaria.render.audio.clips_mid_word", side_effect=spy):
            render.render_all(self.d, ["youtube"])

        self.assertEqual(len(durations_seen), 1)
        # O arquivo visto pela checagem não pode já ter os +3.5s do card —
        # senão ela está medindo o instante errado.
        self.assertLess(durations_seen[0], 5.0 + config.CARD_DURATION_S,
                        "clips_mid_word recebeu o arquivo já concatenado com o "
                        "card — a checagem precisa rodar ANTES do concat")

        out = os.path.join(layout.platform(self.d, "youtube_shorts"), "c1_short.mp4")
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out], capture_output=True, text=True, check=True)
        self.assertGreater(float(r.stdout.strip()), config.CARD_DURATION_S + 3.0)

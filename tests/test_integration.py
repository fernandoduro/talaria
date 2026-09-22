"""Integração: transcrição .txt -> curation -> moments.json -> render.

Usa vídeo sintético gerado com ffmpeg — não depende de rede nem do Drive.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from talaria import curation, episode, layout, texts, txt_parse

TRANSCRIPT = """0:00
Primeira fala do host apresentando o episódio de teste.
0:10
>> Resposta do convidado que começa aqui e segue por um bom tempo.
0:20
Continuação da resposta do convidado com mais detalhes concretos.
0:30
Ainda o convidado, desenvolvendo o raciocínio até o fim da ideia.
0:40
E aqui ele fecha o pensamento com uma conclusão clara.
1:10
>> Nova pergunta do host para começar outro assunto.
"""


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


class TestFluxoCompleto(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        self.txt = layout.ensure_dir(layout.transcript_txt(self.pd))
        with open(self.txt, "w", encoding="utf-8") as f:
            f.write(TRANSCRIPT)

    def tearDown(self):
        shutil.rmtree(self.pd, ignore_errors=True)

    def test_parse_gera_transcricao_json(self):
        segs = txt_parse.parse_txt(self.txt, total_duration=80.0)
        self.assertGreater(len(segs), 0)
        self.assertEqual(segs[-1]["end"], 80.0)

    def test_fluxo_curadoria_ate_momentos(self):
        segs = txt_parse.parse_txt(self.txt, total_duration=80.0)
        estado = curation.new_state(meta=1)

        clip = {"slug": "corte1", "start": segs[0]["start"], "end": segs[-1]["end"],
                 "kind": "story", "screen_text": "Teste de corte"}
        curation.approve(estado, clip)
        self.assertTrue(curation.is_closed(estado))

        path = curation.save_moments(self.pd, estado)
        with open(path, encoding="utf-8") as f:
            moments = json.load(f)
        self.assertEqual(moments[0]["slug"], "corte1")

    def test_rejeitado_nao_volta(self):
        estado = curation.new_state(meta=5)
        curation.reject(estado, {"start": 0.0, "end": 70.0}, "gancho fraco")
        self.assertTrue(curation.is_burned((5.0, 75.0), estado))
        self.assertFalse(curation.is_burned((200.0, 270.0), estado))

    def test_thumb_args_do_episodio(self):
        episode.save(self.pd, {
            "season": 2, "episode": 7, "company": "Zarvik",
            "cidade": "Ribeirão Açaí", "uf": "SP",
            "guests": [{"name": "Teresa", "role": "sócio", "linkedin": ""}],
        })
        args = texts.thumb_args(self.pd)
        self.assertEqual(args["l2"], "T2E07")

    @unittest.skipUnless(has_ffmpeg(), "ffmpeg não disponível")
    def test_render_com_video_sintetico(self):
        from talaria import render

        video = layout.ensure_dir(layout.video(self.pd))
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:d=8:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-shortest", video,
        ], check=True)

        segs = [{"start": 0.5, "end": 4.0, "text": "Legenda de teste.", "turn": False},
                {"start": 4.0, "end": 7.5, "text": "Segunda legenda.", "turn": True}]
        with open(layout.ensure_dir(layout.transcript(self.pd)), "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f)
        with open(layout.ensure_dir(layout.moments(self.pd)), "w", encoding="utf-8") as f:
            json.dump([{"slug": "c1", "start": 0.0, "end": 8.0}], f)

        render.render_all(self.pd, ["youtube"])
        out = os.path.join(layout.platform(self.pd, "youtube_shorts"), "c1_short.mp4")
        self.assertTrue(os.path.exists(out))
        self.assertGreater(os.path.getsize(out), 1000)

    def test_post_gerar_produz_os_arquivos(self):
        """Fluxo do comando: posts.json -> PNGs em instagram_posts/."""
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as base:
            proj = os.path.join(base, "epteste")
            os.makedirs(proj)
            with open(layout.ensure_dir(layout.episode(proj)), "w", encoding="utf-8") as f:
                json.dump({"season": 2, "episode": 8, "company": "Zarvik",
                           "cidade": "Ribeirão Açaí", "uf": "SP", "topics": [],
                           "guests": [{"name": "Marina Siqueira",
                                           "role": "Sócio"}]}, f, ensure_ascii=False)
            with open(layout.ensure_dir(layout.posts(proj)), "w", encoding="utf-8") as f:
                json.dump({"posts": [{"slug": "c1", "cards": ["Curta e boa."]}]},
                          f, ensure_ascii=False)

            from talaria import post_instagram
            gerados = post_instagram.generate(proj)
            self.assertEqual(len(gerados), 1)
            self.assertTrue(os.path.exists(
                os.path.join(layout.posts_png(proj), "post_c1.png")))


if __name__ == "__main__":
    unittest.main()


class TestMigracaoAutomatica(unittest.TestCase):
    """Episódio da estrutura antiga é reorganizado sem o gestor pedir."""

    def test_comando_migra_projeto_antigo(self):
        import json
        import os
        import tempfile
        from talaria import layout

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "moments.json"), "w", encoding="utf-8") as f:
                json.dump([], f)
            layout.migrate(d)
            self.assertTrue(os.path.exists(layout.moments(d)))
            self.assertFalse(os.path.exists(os.path.join(d, "moments.json")))

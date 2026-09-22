"""Testes do orquestrador de publicação."""
import json
import os
import tempfile
import unittest
from unittest import mock

from talaria import layout, publish

ENV_OK = {"IG_PAGE_TOKEN": "t", "IG_BUSINESS_ACCOUNT_ID": "1",
          "S3_PUBLISH_BUCKET": "b", "YT_CLIENT_SECRET_PATH": "/x",
          "YT_REFRESH_TOKEN": "r"}


def _project(pd, title="Titulo do Short"):
    """Projeto completo: moments, posts, agenda e arquivos em publish/."""
    moments = [{"slug": "corte1", "start": 1.0, "end": 70.0,
                 "title": title}]
    with open(layout.ensure_dir(layout.moments(pd)), "w", encoding="utf-8") as f:
        json.dump(moments, f)
    with open(layout.ensure_dir(layout.posts(pd)), "w", encoding="utf-8") as f:
        json.dump({"posts": [{"slug": "cit_x", "cards": ["a", "b"],
                              "legenda": "leg"}]}, f)
    with open(layout.ensure_dir(layout.schedule(pd)), "w", encoding="utf-8") as f:
        json.dump({"agenda": [
            {"data": "2026-08-24", "kind": "clip", "slug": "corte1"},
            {"data": "2026-08-24", "kind": "post", "slug": "cit_x"},
        ]}, f)
    # peças renderizadas + captions
    for pasta, name in (("youtube_shorts", "corte1_short"),
                        ("instagram_reels", "corte1_reel")):
        base = os.path.join(layout.platform(pd, pasta), name)
        layout.ensure_dir(base + ".mp4")
        open(base + ".mp4", "w").close()
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write("Legenda do clip.\n\n#Tag")
    pasta = layout.posts_png(pd)
    os.makedirs(pasta, exist_ok=True)
    for n in ("post_cit_x_1.png", "post_cit_x_2.png"):
        open(os.path.join(pasta, n), "w").close()
    with open(os.path.join(pasta, "post_cit_x.txt"), "w",
              encoding="utf-8") as f:
        f.write("Legenda do post.\n\n#Tag")


class TestPreChecagem(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)

    @mock.patch.dict("os.environ", ENV_OK)
    def test_projeto_completo_passa(self):
        import datetime as dt
        from talaria import schedule
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual(publish.precheck(self.pd, pares), [])

    @mock.patch.dict("os.environ", ENV_OK)
    def test_mp4_faltando_aponta_o_render(self):
        import datetime as dt
        from talaria import schedule
        os.remove(os.path.join(layout.platform(self.pd, "youtube_shorts"),
                               "corte1_short.mp4"))
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        self.assertTrue(any("render" in e for e in erros))

    @mock.patch.dict("os.environ", ENV_OK)
    def test_corte_sem_titulo_aponta_a_curadoria(self):
        import datetime as dt
        from talaria import schedule
        _project(self.pd, title="")
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        self.assertTrue(any("title" in e and "curation" in e for e in erros))

    @mock.patch.dict("os.environ", ENV_OK)
    def test_titulo_acima_de_100_aborta(self):
        import datetime as dt
        from talaria import schedule
        _project(self.pd, title="x" * 101)
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        self.assertTrue(any("100" in e for e in erros))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_credencial_faltando_lista_as_variaveis(self):
        import datetime as dt
        from talaria import schedule
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        texto = "\n".join(erros)
        for var in ("IG_PAGE_TOKEN", "YT_REFRESH_TOKEN", "S3_PUBLISH_BUCKET"):
            self.assertIn(var, texto)

    @mock.patch.dict("os.environ", {**ENV_OK, "YT_PRIVACY": "unlised"})
    def test_yt_privacy_invalido_reprova_antes_de_subir(self):
        # Typo na privacy tem que aparecer ANTES do upload: descoberto
        # depois, o vídeo já estaria no ar com a privacy errada.
        import datetime as dt
        from talaria import schedule
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        self.assertTrue(any("YT_PRIVACY" in e for e in erros))

    @mock.patch.dict("os.environ", {**ENV_OK, "YT_PRIVACY": "unlisted"})
    def test_yt_privacy_valido_passa(self):
        import datetime as dt
        from talaria import schedule
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual(publish.precheck(self.pd, pares), [])

    @mock.patch.dict("os.environ", ENV_OK)
    def test_png_do_post_faltando_aponta_o_gerar(self):
        import datetime as dt
        from talaria import schedule
        pasta = layout.posts_png(self.pd)
        for n in os.listdir(pasta):
            if n.endswith(".png"):
                os.remove(os.path.join(pasta, n))
        pares = schedule.pending(self.pd, dia=dt.date(2026, 8, 24))
        erros = publish.precheck(self.pd, pares)
        self.assertTrue(any("post --generate" in e for e in erros))


class TestPngsDoPost(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)

    def test_carrossel_ordenado_numericamente(self):
        pasta = layout.posts_png(self.pd)
        # _10 depois de _2: ordenação NUMÉRICA, não alfabética
        for n in ("post_cit_x_10.png",):
            open(os.path.join(pasta, n), "w").close()
        pngs = publish._post_pngs(self.pd, "cit_x")
        nomes = [os.path.basename(p) for p in pngs]
        self.assertEqual(nomes, ["post_cit_x_1.png", "post_cit_x_2.png",
                                 "post_cit_x_10.png"])


@mock.patch.dict("os.environ", ENV_OK)
@mock.patch("talaria.publish.publish_instagram")
@mock.patch("talaria.publish.publish_youtube")
class TestExecutar(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)
        self.dia = __import__("datetime").date(2026, 8, 24)

    def test_publica_tudo_e_registra_cada_um(self, yt, ig):
        yt.upload.return_value = {"id": "v1", "url": "https://yt/v1"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "https://ig/r1"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "https://ig/p1"}
        resultados = publish.execute(self.pd, dia=self.dia)
        self.assertEqual([r["ok"] for r in resultados], [True, True, True])
        from talaria import published
        reg = published.carrega(self.pd)
        self.assertTrue(published.is_published(reg, "youtube_shorts", "corte1"))
        self.assertTrue(published.is_published(reg, "instagram_reels", "corte1"))
        self.assertTrue(published.is_published(reg, "instagram_posts", "cit_x"))
        # título veio do moments.json, descrição do .txt
        args = yt.upload.call_args[0]
        self.assertEqual(args[1], "Titulo do Short")
        self.assertIn("Legenda do clip.", args[2])

    def test_falha_numa_plataforma_nao_trava_as_outras(self, yt, ig):
        yt.upload.side_effect = RuntimeError("quota estourada")
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        resultados = publish.execute(self.pd, dia=self.dia)
        por_pl = {r["platform"]: r["ok"] for r in resultados}
        self.assertFalse(por_pl["youtube_shorts"])
        self.assertTrue(por_pl["instagram_reels"])
        self.assertTrue(por_pl["instagram_posts"])
        # o que falhou NÃO entra no registro — retenta amanhã
        from talaria import published
        reg = published.carrega(self.pd)
        self.assertFalse(published.is_published(reg, "youtube_shorts", "corte1"))

    def test_registro_e_imediato_nao_no_fim_do_lote(self, yt, ig):
        # Se o processo morrer no item 2, o item 1 já está registrado.
        from talaria import published
        estado = {}

        def upload_ok(*a, **k):
            return {"id": "v1", "url": "u"}

        def reel_explode(*a, **k):
            # neste ponto o YouTube JÁ deve estar registrado
            reg = published.carrega(self.pd)
            estado["yt_registrado"] = published.is_published(
                reg, "youtube_shorts", "corte1")
            raise RuntimeError("boom")

        yt.upload.side_effect = upload_ok
        ig.publish_reel.side_effect = reel_explode
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        publish.execute(self.pd, dia=self.dia)
        self.assertTrue(estado["yt_registrado"])

    def test_registro_que_falha_depois_do_ar_nao_vira_retentativa(self, yt, ig):
        # O pior caso do módulo: o vídeo SUBIU e o registro falhou (disco
        # cheio). Marcar ok=False mandaria o par pra fila de amanhã e o
        # publicaria de novo — duplicata que não tem correção. Tem que sair
        # como published, gritando que o registro precisa de conserto à mão.
        yt.upload.return_value = {"id": "v1", "url": "https://yt/v1"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        with mock.patch("talaria.publish.published.record",
                        side_effect=OSError("disco cheio")):
            resultados = publish.execute(self.pd, dia=self.dia)

        yt_r = [r for r in resultados if r["platform"] == "youtube_shorts"][0]
        self.assertTrue(yt_r["ok"])           # está no ar: não é falha
        self.assertTrue(yt_r["record_failed"])
        self.assertEqual(yt_r["id"], "v1")    # id para o conserto manual
        self.assertIn("disco cheio", yt_r["error"])

    def test_publicacao_normal_nao_marca_registro_falhou(self, yt, ig):
        yt.upload.return_value = {"id": "v1", "url": "u"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        resultados = publish.execute(self.pd, dia=self.dia)
        self.assertTrue(all(not r.get("record_failed") for r in resultados))

    def test_pre_checagem_reprovada_nao_publica_nada(self, yt, ig):
        os.remove(os.path.join(layout.platform(self.pd, "youtube_shorts"),
                               "corte1_short.mp4"))
        with self.assertRaises(ValueError):
            publish.execute(self.pd, dia=self.dia)
        yt.upload.assert_not_called()
        ig.publish_reel.assert_not_called()
        ig.publish_post.assert_not_called()

    def test_nada_pendente_devolve_vazio(self, yt, ig):
        futuro = __import__("datetime").date(2026, 8, 1)
        self.assertEqual(publish.execute(self.pd, dia=futuro), [])
        yt.upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()

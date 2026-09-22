"""Testes do registro de publicação (a trava contra post duplicado)."""
import json
import os
import tempfile
import unittest

from talaria import layout, published


class TestCarrega(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_sem_arquivo_devolve_vazio(self):
        # Projeto que nunca publicou: registro vazio, sem error.
        self.assertEqual(published.load(self.pd), {})

    def test_corrompido_aborta_fail_closed(self):
        # JSON inválido NUNCA vira "nada published" — republicaria tudo.
        path = layout.ensure_dir(layout.published(self.pd))
        with open(path, "w", encoding="utf-8") as f:
            f.write("{metade de um json")
        with self.assertRaises(RuntimeError) as ctx:
            published.load(self.pd)
        self.assertIn("corrompido", str(ctx.exception))


class TestRegistra(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_grava_na_hora_e_rele(self):
        published.record(self.pd, "youtube_shorts", "corte1", "abc123",
                           "https://youtube.com/shorts/abc123")
        reg = published.load(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        r = reg["youtube_shorts"][0]
        self.assertEqual(r["slug"], "corte1")
        self.assertEqual(r["id"], "abc123")
        self.assertIn("published_at", r)

    def test_acumula_sem_perder_os_anteriores(self):
        published.record(self.pd, "youtube_shorts", "corte1", "a", "u1")
        published.record(self.pd, "instagram_reels", "corte1", "b", "u2")
        reg = published.load(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        self.assertEqual(len(reg["instagram_reels"]), 1)

    def test_escrita_atomica_nao_deixa_tmp(self):
        # temp + os.replace: ou o arquivo novo inteiro, ou o antigo intacto.
        published.record(self.pd, "instagram_posts", "post_x", "c", "u3")
        pasta = os.path.dirname(layout.published(self.pd))
        sobras = [n for n in os.listdir(pasta) if n.endswith(".tmp")]
        self.assertEqual(sobras, [])


class TestJaPublicado(unittest.TestCase):
    def test_encontra_por_plataforma_e_slug(self):
        reg = {"youtube_shorts": [{"slug": "corte1", "id": "a"}]}
        self.assertTrue(published.is_published(reg, "youtube_shorts", "corte1"))
        # Mesma peça, platform diferente: NÃO conta — a unidade de pendência
        # é (slug, platform). Corte meio published retenta só o que faltou.
        self.assertFalse(published.is_published(reg, "instagram_reels", "corte1"))
        self.assertFalse(published.is_published(reg, "youtube_shorts", "corte2"))
        self.assertFalse(published.is_published({}, "youtube_shorts", "corte1"))


if __name__ == "__main__":
    unittest.main()

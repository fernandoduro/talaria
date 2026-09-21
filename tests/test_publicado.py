"""Testes do registro de publicação (a trava contra post duplicado)."""
import json
import os
import tempfile
import unittest

from talaria import layout, publicado


class TestCarrega(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_sem_arquivo_devolve_vazio(self):
        # Projeto que nunca publicou: registro vazio, sem erro.
        self.assertEqual(publicado.carrega(self.pd), {})

    def test_corrompido_aborta_fail_closed(self):
        # AP-21: JSON inválido NUNCA vira "nada publicado" — republicaria tudo.
        path = layout.garante(layout.publicado(self.pd))
        with open(path, "w", encoding="utf-8") as f:
            f.write("{metade de um json")
        with self.assertRaises(RuntimeError) as ctx:
            publicado.carrega(self.pd)
        self.assertIn("corrompido", str(ctx.exception))


class TestRegistra(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_grava_na_hora_e_rele(self):
        publicado.registra(self.pd, "youtube_shorts", "corte1", "abc123",
                           "https://youtube.com/shorts/abc123")
        reg = publicado.carrega(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        r = reg["youtube_shorts"][0]
        self.assertEqual(r["slug"], "corte1")
        self.assertEqual(r["id"], "abc123")
        self.assertIn("publicado_em", r)

    def test_acumula_sem_perder_os_anteriores(self):
        publicado.registra(self.pd, "youtube_shorts", "corte1", "a", "u1")
        publicado.registra(self.pd, "instagram_reels", "corte1", "b", "u2")
        reg = publicado.carrega(self.pd)
        self.assertEqual(len(reg["youtube_shorts"]), 1)
        self.assertEqual(len(reg["instagram_reels"]), 1)

    def test_escrita_atomica_nao_deixa_tmp(self):
        # temp + os.replace: ou o arquivo novo inteiro, ou o antigo intacto.
        publicado.registra(self.pd, "instagram_posts", "post_x", "c", "u3")
        pasta = os.path.dirname(layout.publicado(self.pd))
        sobras = [n for n in os.listdir(pasta) if n.endswith(".tmp")]
        self.assertEqual(sobras, [])


class TestJaPublicado(unittest.TestCase):
    def test_encontra_por_plataforma_e_slug(self):
        reg = {"youtube_shorts": [{"slug": "corte1", "id": "a"}]}
        self.assertTrue(publicado.ja_publicado(reg, "youtube_shorts", "corte1"))
        # Mesma peça, plataforma diferente: NÃO conta — a unidade de pendência
        # é (slug, plataforma). Corte meio publicado retenta só o que faltou.
        self.assertFalse(publicado.ja_publicado(reg, "instagram_reels", "corte1"))
        self.assertFalse(publicado.ja_publicado(reg, "youtube_shorts", "corte2"))
        self.assertFalse(publicado.ja_publicado({}, "youtube_shorts", "corte1"))


if __name__ == "__main__":
    unittest.main()

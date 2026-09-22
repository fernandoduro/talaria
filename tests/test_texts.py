"""Testes da leitura de texts.json para a thumbnail."""
import inspect
import json
import os
import tempfile
import unittest

from talaria import layout, texts, thumbnail


class TestTextos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "episode.json"), "w", encoding="utf-8") as f:
            json.dump({
                "season": 2, "episode": 7, "company": "Zarvik",
                "cidade": "Ribeirão Açaí", "uf": "SP",
                "guests": [{"name": "Teresa", "role": "sócio", "linkedin": ""}],
            }, f)

    def test_thumb_args_a_partir_do_episodio(self):
        args = texts.thumb_args(self.d)
        self.assertEqual(args["l1"], "Zarvik")
        self.assertEqual(args["l2"], "T2E07")
        self.assertIn("Ribeirão Açaí", args["subtitle"])
        self.assertIn("Teresa", args["credits"])

    def test_textos_json_sobrescreve_episodio(self):
        with open(layout.ensure_dir(layout.texts(self.d)), "w", encoding="utf-8") as f:
            json.dump({"thumb": {"l1": "CUSTOMIZADO", "l2": "T2E07"}}, f)
        args = texts.thumb_args(self.d)
        self.assertEqual(args["l1"], "CUSTOMIZADO")

    def test_selo_tem_codigo_do_episodio(self):
        args = texts.thumb_args(self.d)
        self.assertIn("T2E07", args["badge"])

    def test_salvar_e_ler(self):
        texts.save(self.d, {"title": "X", "description": "Y"})
        t = texts.load(self.d)
        self.assertEqual(t["title"], "X")

    def test_load_sem_arquivo_retorna_vazio(self):
        self.assertEqual(texts.load(tempfile.mkdtemp()), {})

    def test_l1_cai_no_tema_quando_nao_ha_empresa(self):
        """Sem convidado externo, a linha 1 recebe o tema do episódio."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "episode.json"), "w", encoding="utf-8") as f:
            json.dump({
                "season": 3, "episode": 1, "company": "",
                "cidade": "Pedra Nova", "uf": "SP", "guests": [],
                "topics": ["ecossistema local de startups", "outro"],
            }, f)
        args = texts.thumb_args(d)
        self.assertEqual(args["l1"], "ecossistema local de startups")

    def test_build_kwargs_bate_com_a_assinatura_do_thumbnail(self):
        """Traduz l1/l2 -> headline_l1/headline_l2 sem perder campo em silêncio."""
        kwargs = texts.build_kwargs(self.d)
        sig = inspect.signature(thumbnail.build_thumbnail)
        esperados = {n for n, p in sig.parameters.items()
                     if p.kind is inspect.Parameter.KEYWORD_ONLY}
        self.assertEqual(set(kwargs), esperados)

    def test_build_kwargs_traduz_os_valores(self):
        kwargs = texts.build_kwargs(self.d)
        self.assertEqual(kwargs["headline_l1"], "Zarvik")
        self.assertEqual(kwargs["headline_l2"], "T2E07")
        self.assertIn("Teresa", kwargs["credits"])


if __name__ == "__main__":
    unittest.main()
